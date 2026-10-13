"""Profile Matching Agent — scores each job against the user profile."""

from collections import Counter
from typing import Literal

from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

from agents.model_client import create_chat_model, parse_structured_response
from config.settings import settings
from domain.job_formatting import format_job
from domain.models import JobPosting, MatchResult
from observability.logging import get_logger
from prompts.prompt import load_prompt

logger = get_logger(__name__)


def get_prompt(*, client=None, version: int | None = None, allow_fallback: bool = True):
    """Load the matcher template and enforce this agent's input contract."""
    prompt = load_prompt(
        "matcher",
        client,
        version=version,
        allow_fallback=allow_fallback,
    )
    if set(prompt.input_variables) != {"profile", "criteria", "discard_keywords", "jobs"}:
        raise ValueError("Matcher prompt must use profile, criteria, discard_keywords and jobs")
    return prompt


class MatchItem(BaseModel):
    """Model response fields; the original job is attached after ID validation."""

    job_id: str = Field(description="The job's id field")
    score: float = Field(ge=0.0, le=1.0, description="How well it matches overall, 0.0–1.0")
    matching_skills: list[str] = Field(
        default_factory=list, description="Skills the user has that the job requires"
    )
    missing_skills: list[str] = Field(
        default_factory=list, description="Skills the job requires that the user lacks"
    )
    match_reason: str = Field(
        default="", description="1-2 sentences; name which blocker triggered if score is 0"
    )
    recommendation: Literal["Strong Match", "Good Match", "Weak Match", "Skip"]


class MatchesResponse(BaseModel):
    """Submit match results for all provided job postings."""

    matches: list[MatchItem] = Field(description="Exactly one entry per job posting provided")


def _format_jobs(jobs: list[JobPosting]) -> str:
    return (
        "\n\n".join(
            format_job(job, description_chars=settings.matcher_description_chars) for job in jobs
        )
        + "\n"
    )


def _to_match_results(response: MatchesResponse, jobs: list[JobPosting]) -> list[MatchResult]:
    """Validate batch coverage before joining response fields to original jobs."""
    jobs_by_id = {job.id: job for job in jobs}
    counts = Counter(item.job_id for item in response.matches)
    missing = sorted(jobs_by_id.keys() - counts.keys())
    unknown = sorted(counts.keys() - jobs_by_id.keys())
    duplicates = sorted(job_id for job_id, count in counts.items() if count > 1)
    if missing or unknown or duplicates:
        raise ValueError(
            f"Matcher response does not cover the batch exactly once: "
            f"missing={missing}, unknown={unknown}, duplicates={duplicates}"
        )
    return [
        MatchResult(
            job=jobs_by_id[item.job_id],
            **item.model_dump(exclude={"job_id"}),
        )
        for item in response.matches
    ]


def run(
    jobs: list[JobPosting],
    profile_md: str,
    criteria_md: str,
    discard_keywords: str = "",
    *,
    prompt_version: int | None = None,
    allow_prompt_fallback: bool = True,
) -> list[MatchResult]:
    if not jobs:
        logger.warning("matcher_no_jobs")
        return []

    # A one-result-per-ID contract requires unique IDs in the supplied jobs.
    counts = Counter(job.id for job in jobs)
    duplicates = sorted(job_id for job_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Matcher input contains duplicate job IDs: {duplicates}")

    # Keyword hints must not reject jobs before the full input-file policy is applied.
    results: list[MatchResult] = []

    # Build one model and reuse it across independent job groups.
    model = create_chat_model(
        settings.matcher_model,
        max_tokens=4096,
        stage="matcher",
    )
    structured_model = model.with_structured_output(
        MatchesResponse, method="json_schema", include_raw=True
    )
    prompt = get_prompt(version=prompt_version, allow_fallback=allow_prompt_fallback)
    chain = prompt | structured_model

    batches = [
        jobs[i : i + settings.matcher_batch_size]
        for i in range(0, len(jobs), settings.matcher_batch_size)
    ]
    logger.info(
        "matcher_batches_start",
        batches=len(batches),
        max_concurrency=settings.matcher_max_concurrency,
    )
    progress = get_stream_writer()
    progress({"kind": "matching", "completed": 0, "total": len(batches)})
    responses = [None] * len(batches)
    for completed, (batch_index, response) in enumerate(
        chain.batch_as_completed(
            [
                {
                    "profile": profile_md,
                    "criteria": criteria_md,
                    "discard_keywords": discard_keywords or "(none)",
                    "jobs": _format_jobs(batch),
                }
                for batch in batches
            ],
            config={"max_concurrency": settings.matcher_max_concurrency},
        ),
        start=1,
    ):
        responses[batch_index] = response
        progress({"kind": "matching", "completed": completed, "total": len(batches)})
    # Restore input order after streaming each completed request.
    for index, (batch, response) in enumerate(zip(batches, responses, strict=True), start=1):
        parsed = parse_structured_response(response, MatchesResponse)
        results.extend(_to_match_results(parsed, batch))
        logger.info("matcher_batch_done", batch=index, batch_size=len(batch))

    logger.info(
        "matcher_complete",
        total=len(results),
        strong=sum(1 for r in results if r.recommendation == "Strong Match"),
        good=sum(1 for r in results if r.recommendation == "Good Match"),
    )
    return results

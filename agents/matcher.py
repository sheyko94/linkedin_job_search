"""Profile Matching Agent — scores each job against the user profile."""

from collections import Counter
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.model_client import create_chat_model
from agents.models import JobPosting, MatchResult
from config.job_formatting import format_job
from config.logging import get_logger
from config.reader import load_discard_keywords
from config.settings import settings

logger = get_logger(__name__)

# A discard keyword only disqualifies via description when it appears near requirement
# language — so "AWS or Azure a plus" is ignored but "4+ years of experience with Azure"
# is not. (The same list also pre-filters by title in the search agent, before fetching.)
_REQUIREMENT_CUES = (
    "year",
    "yrs",
    "required",
    "must have",
    "must-have",
    "minimum",
    "at least",
    "proven experience",
    "strong experience",
    "extensive experience",
    "hands-on experience",
)
# How many characters on each side of a skill mention to scan for requirement cues.
_REQUIREMENT_WINDOW = 80


def _dealbreaker_hit(description: str, skills: set[str]) -> str | None:
    """Return the dealbreaker skill the description hard-requires, or None.

    Matches only when the skill appears within `_REQUIREMENT_WINDOW` chars of a
    requirement cue (see `_REQUIREMENT_CUES`), to avoid skipping casual mentions.
    """
    if not description or not skills:
        return None
    text = description.lower()
    for skill in skills:
        idx = text.find(skill)
        while idx != -1:
            start = max(0, idx - _REQUIREMENT_WINDOW)
            window = text[start : idx + len(skill) + _REQUIREMENT_WINDOW]
            if any(cue in window for cue in _REQUIREMENT_CUES):
                return skill
            idx = text.find(skill, idx + 1)
    return None


_SYSTEM = """\
You are a job profile matching agent. Given a list of job postings and a user profile, \
evaluate how well each job matches the user's skills, experience, and preferences.

HARD BLOCKER RULES — apply before scoring. If any blocker is triggered, set score to 0.0 \
and recommendation to "Skip", regardless of skill fit:
1. Work mode is on-site or hybrid, or the posting does not mention remote at all → Skip
2. Job type is full-time permanent (not contract, not part-time, not temporary, \
not freelance, not ZZP, \
   not contractor, not interim) → Skip. \
   Note: in the Netherlands, ZZP and contractor are equivalent to freelance — treat \
them as acceptable.
   LinkedIn's full-time label describes working hours; it does not prove permanent employment.
   Read the engagement evidence and description. CONTRACT: Contractor assignment with \
COMMITMENT: Full-time is an acceptable contract. Do not trigger this blocker solely \
from full-time metadata. If explicit engagement statements conflict, explain the ambiguity \
and assess the role's actual terms rather than assuming permanent employment.
3. The posting restricts candidates to a specific location that is not the Netherlands → Skip. \
   Only continue if the role is based in the Netherlands, or the posting has no \
geographic restriction \
   on where the candidate must live (true worldwide remote).
4. Role is primarily frontend, mobile, or QA → Skip

Produce one result object for every job you were given, including skipped jobs. \
Return the full list using the provided structured response schema.\
"""


_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "## User Profile\n{profile}\n\n## Job Postings\n{jobs}"),
    ]
)


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


def run(jobs: list[JobPosting], profile_md: str) -> list[MatchResult]:
    if not jobs:
        logger.warning("matcher_no_jobs")
        return []

    # A one-result-per-ID contract requires unique IDs in the supplied jobs.
    counts = Counter(job.id for job in jobs)
    duplicates = sorted(job_id for job_id, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Matcher input contains duplicate job IDs: {duplicates}")

    # Deterministic pre-filter: hard-skip jobs whose description requires a discard
    # keyword as a stated requirement, before spending tokens scoring them.
    discard_keywords = load_discard_keywords()
    results: list[MatchResult] = []
    to_score: list[JobPosting] = []
    for job in jobs:
        hit = _dealbreaker_hit(job.description, discard_keywords)
        if hit:
            results.append(
                MatchResult(
                    job=job,
                    score=0.0,
                    matching_skills=[],
                    missing_skills=[hit],
                    match_reason=(
                        f"Auto-skip: posting hard-requires '{hit}', "
                        "which the profile does not demonstrate."
                    ),
                    recommendation="Skip",
                )
            )
            logger.info("matcher_dealbreaker_skip", job_id=job.id, skill=hit)
        else:
            to_score.append(job)

    # Build the model only when some jobs need scoring, and reuse it across batches.
    if to_score:
        model = create_chat_model(
            settings.matcher_model,
            max_tokens=4096,
            stage="matcher",
            tool_name=MatchesResponse.__name__,
        )
        structured_model = model.with_structured_output(
            MatchesResponse, method="function_calling", include_raw=True
        )
        chain = _PROMPT | structured_model

    for i in range(0, len(to_score), settings.matcher_batch_size):
        batch = to_score[i : i + settings.matcher_batch_size]
        response = chain.invoke({"profile": profile_md, "jobs": _format_jobs(batch)})
        # include_raw retains parsing failures for inspection; propagate them here.
        if response["parsing_error"] is not None:
            raise response["parsing_error"]
        parsed = response["parsed"]
        if not isinstance(parsed, MatchesResponse):
            raise ValueError("Matcher model did not return the structured response")
        results.extend(_to_match_results(parsed, batch))
        logger.info(
            "matcher_batch_done", batch=i // settings.matcher_batch_size + 1, batch_size=len(batch)
        )

    logger.info(
        "matcher_complete",
        total=len(results),
        strong=sum(1 for r in results if r.recommendation == "Strong Match"),
        good=sum(1 for r in results if r.recommendation == "Good Match"),
    )
    return results

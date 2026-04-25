"""Profile Matching Agent — scores each job against the user profile."""

from agents.models import JobPosting, MatchResult
from config.logging import get_logger
from config.settings import settings
from llm import client as llm

logger = get_logger(__name__)

_SYSTEM = """\
You are a job profile matching agent. Given a list of job postings and a user profile, \
evaluate how well each job matches the user's skills, experience, and preferences.

HARD BLOCKER RULES — apply before scoring. If any blocker is triggered, set score to 0.0 \
and recommendation to "Skip", regardless of skill fit:
1. Work mode is on-site or hybrid, or the posting does not mention remote at all → Skip
2. Job type is full-time permanent (not contract, not part-time, not temporary, not freelance, not ZZP, \
   not contractor, not interim) → Skip. \
   Note: in the Netherlands, ZZP and contractor are equivalent to freelance — treat them as acceptable.
3. The posting restricts candidates to a specific location that is not the Netherlands → Skip. \
   Only continue if the role is based in the Netherlands, or the posting has no geographic restriction \
   on where the candidate must live (true worldwide remote).
5. Role is primarily frontend, mobile, or QA → Skip

For all other jobs, output a JSON object with:
- job_id: the job's id field
- score: float 0.0–1.0 (how well it matches overall)
- matching_skills: list of skills the user has that the job requires
- missing_skills: list of skills the job requires that the user lacks
- match_reason: 1-2 sentence explanation, naming which blocker triggered if score is 0
- recommendation: one of "Strong Match" (≥0.75), "Good Match" (≥0.5), "Weak Match" (≥0.25), "Skip" (<0.25)

Respond with a JSON array of these objects. No markdown, no extra text.\
"""


def _format_jobs(jobs: list[JobPosting]) -> str:
    lines = []
    for j in jobs:
        lines.append(f"### Job ID: {j.id}")
        lines.append(f"Title: {j.title}")
        lines.append(f"Company: {j.company}")
        lines.append(f"Location: {j.location}")
        if j.work_mode:
            lines.append(f"Work mode: {j.work_mode}")
        if j.job_type:
            lines.append(f"Job type: {j.job_type}")
        if j.salary_range:
            lines.append(f"Salary: {j.salary_range}")
        if j.description:
            lines.append(f"Description:\n{j.description[:1000]}")
        lines.append("")
    return "\n".join(lines)


def _parse(raw: str, jobs: list[JobPosting]) -> list[MatchResult]:
    jobs_by_id = {j.id: j for j in jobs}
    results = []
    for item in llm.extract_json(raw):
        job_id = str(item.get("job_id", ""))
        job = jobs_by_id.get(job_id)
        if not job:
            continue
        results.append(
            MatchResult(
                job=job,
                score=float(item.get("score", 0.0)),
                matching_skills=item.get("matching_skills", []),
                missing_skills=item.get("missing_skills", []),
                match_reason=item.get("match_reason", ""),
                recommendation=item.get("recommendation", "Skip"),
            )
        )
    return results


def run(jobs: list[JobPosting], profile_md: str) -> list[MatchResult]:
    if not jobs:
        logger.warning("matcher_no_jobs")
        return []

    results: list[MatchResult] = []
    for i in range(0, len(jobs), settings.matcher_batch_size):
        batch = jobs[i : i + settings.matcher_batch_size]
        user_prompt = (
            f"## User Profile\n{profile_md}\n\n"
            f"## Job Postings\n{_format_jobs(batch)}"
        )
        raw = llm.complete(
            system=_SYSTEM,
            user=user_prompt,
            model=settings.matcher_model,
            max_tokens=4096,
        )
        results.extend(_parse(raw, batch))
        logger.info("matcher_batch_done", batch=i // settings.matcher_batch_size + 1, batch_size=len(batch))

    logger.info(
        "matcher_complete",
        total=len(results),
        strong=sum(1 for r in results if r.recommendation == "Strong Match"),
        good=sum(1 for r in results if r.recommendation == "Good Match"),
    )
    return results

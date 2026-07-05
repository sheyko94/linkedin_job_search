"""Profile Matching Agent — scores each job against the user profile."""

from agents.models import JobPosting, MatchResult
from config.logging import get_logger
from config.reader import load_discard_keywords
from config.settings import settings
from llm import anthropic as llm

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
3. The posting restricts candidates to a specific location that is not the Netherlands → Skip. \
   Only continue if the role is based in the Netherlands, or the posting has no \
geographic restriction \
   on where the candidate must live (true worldwide remote).
5. Role is primarily frontend, mobile, or QA → Skip

For all other jobs, produce one result object per job. Return every job you were given by \
calling the `submit_matches` tool exactly once with the full list.\
"""

_TOOL_NAME = "submit_matches"
_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "description": "One entry per job posting provided.",
            "items": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job's id field"},
                    "score": {
                        "type": "number",
                        "description": "How well it matches overall, 0.0–1.0",
                    },
                    "matching_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Skills the user has that the job requires",
                    },
                    "missing_skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Skills the job requires that the user lacks",
                    },
                    "match_reason": {
                        "type": "string",
                        "description": "1-2 sentences; name which blocker triggered if score is 0",
                    },
                    "recommendation": {
                        "type": "string",
                        "enum": ["Strong Match", "Good Match", "Weak Match", "Skip"],
                    },
                },
                "required": ["job_id", "score", "recommendation"],
            },
        }
    },
    "required": ["matches"],
}


# Descriptions are truncated to this length before being shown to the matcher.
# Must be long enough to include the requirements/qualifications block, which usually
# follows the role intro — truncating too early hides hard requirements (e.g. "4+ years
# Azure") and inflates scores. The upstream fetch caps descriptions at 8000 chars.
DESCRIPTION_CHARS = 5000


def format_job(j: JobPosting) -> str:
    """Render the exact per-job context the matcher LLM receives for its decision."""
    lines = [
        f"### Job ID: {j.id}",
        f"Title: {j.title}",
        f"Company: {j.company}",
        f"Location: {j.location}",
    ]
    if j.work_mode:
        lines.append(f"Work mode: {j.work_mode}")
    if j.job_type:
        lines.append(f"Job type: {j.job_type}")
    if j.salary_range:
        lines.append(f"Salary: {j.salary_range}")
    if j.description:
        lines.append(f"Description:\n{j.description[:DESCRIPTION_CHARS]}")
    return "\n".join(lines)


def _format_jobs(jobs: list[JobPosting]) -> str:
    return "\n\n".join(format_job(j) for j in jobs) + "\n"


def _parse(data: dict, jobs: list[JobPosting]) -> list[MatchResult]:
    jobs_by_id = {j.id: j for j in jobs}
    results = []
    for item in data.get("matches", []):
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

    for i in range(0, len(to_score), settings.matcher_batch_size):
        batch = to_score[i : i + settings.matcher_batch_size]
        user_prompt = f"## User Profile\n{profile_md}\n\n## Job Postings\n{_format_jobs(batch)}"
        data = llm.complete_json(
            system=_SYSTEM,
            user=user_prompt,
            model=settings.matcher_model,
            tool_name=_TOOL_NAME,
            input_schema=_INPUT_SCHEMA,
            tool_description="Submit match results for all provided job postings.",
            max_tokens=4096,
        )
        results.extend(_parse(data, batch))
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

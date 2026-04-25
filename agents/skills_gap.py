"""Skills Gap Agent — identifies and categorises missing skills across all matched jobs."""

from agents.models import MatchResult, SkillGap
from config.logging import get_logger
from config.settings import settings
from llm import client as llm

logger = get_logger(__name__)

_SYSTEM = """\
You are a skills gap analysis agent. Given a list of job match results — each including \
the job title, company, and skills the user is missing — identify all distinct missing skills, \
categorise them, count how frequently each appears, and assign a priority.

Categories to use:
- "Programming Language"
- "Framework"
- "Cloud/DevOps"
- "Data & ML"
- "Domain Knowledge"
- "Soft Skill"
- "Other"

Priority rules:
- "High": appears in ≥30% of jobs or is required by top-scoring jobs
- "Medium": appears in 10–29% of jobs
- "Low": appears in <10% of jobs

Respond with a JSON array, each element:
{
  "skill": "<exact skill name>",
  "category": "<category>",
  "frequency": <integer count of jobs that mention this skill>,
  "priority": "High" | "Medium" | "Low"
}

No markdown, no extra text.\
"""


def _format_results(results: list[MatchResult]) -> str:
    lines = [f"Total jobs analysed: {len(results)}", ""]
    for r in results:
        if r.missing_skills:
            lines.append(f"- {r.job.title} @ {r.job.company} (score {r.score:.0%}): missing {', '.join(r.missing_skills)}")
    return "\n".join(lines)


def _parse(raw: str) -> list[SkillGap]:
    return [
        SkillGap(
            skill=item["skill"],
            category=item.get("category", "Other"),
            frequency=int(item.get("frequency", 1)),
            priority=item.get("priority", "Low"),
        )
        for item in llm.extract_json(raw)
    ]


def run(results: list[MatchResult]) -> list[SkillGap]:
    if not results:
        logger.warning("skills_gap_no_results")
        return []

    all_missing = [r for r in results if r.missing_skills]
    if not all_missing:
        logger.info("skills_gap_no_missing_skills")
        return []

    raw = llm.complete(
        system=_SYSTEM,
        user=_format_results(results),
        model=settings.skills_gap_model,
        max_tokens=2048,
    )
    gaps = _parse(raw)
    logger.info("skills_gap_complete", total_gaps=len(gaps), high=sum(1 for g in gaps if g.priority == "High"))
    return gaps

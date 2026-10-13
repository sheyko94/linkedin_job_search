"""Skills Gap Agent — identifies and categorises missing skills across all matched jobs."""

from typing import Literal

from pydantic import BaseModel, Field

from agents.model_client import create_chat_model, parse_structured_response
from config.settings import settings
from domain.models import MatchResult, SkillGap
from observability.logging import get_logger
from prompts.prompt import load_prompt

logger = get_logger(__name__)


class SkillGapItem(BaseModel):
    """Model response contract; defaults preserve the previous parser's behavior."""

    skill: str = Field(description="Exact skill name")
    category: str = "Other"
    frequency: int = Field(default=1, description="Count of jobs that mention this skill")
    priority: Literal["High", "Medium", "Low"] = "Low"


class SkillsGapResponse(BaseModel):
    """Submit the categorised skill gap analysis."""

    gaps: list[SkillGapItem] = Field(description="Distinct missing skills across matched jobs")


def _format_results(results: list[MatchResult]) -> str:
    lines = [f"Total jobs analysed: {len(results)}", ""]
    for r in results:
        if r.missing_skills:
            lines.append(
                f"- {r.job.title} @ {r.job.company} (score {r.score:.0%}): "
                f"missing {', '.join(r.missing_skills)}"
            )
    return "\n".join(lines)


def run(results: list[MatchResult], profile_md: str, criteria_md: str) -> list[SkillGap]:
    if not results:
        logger.warning("skills_gap_no_results")
        return []

    all_missing = [r for r in results if r.missing_skills]
    if not all_missing:
        logger.info("skills_gap_no_missing_skills")
        return []

    model = create_chat_model(
        settings.skills_gap_model,
        max_tokens=2048,
        stage="skills_gap",
        tool_name=SkillsGapResponse.__name__,
    )
    # LangChain derives the tool schema, requests the response, and parses it into
    # Pydantic objects. Raw metadata is retained for our existing execution trace.
    structured_model = model.with_structured_output(
        SkillsGapResponse, method="function_calling", include_raw=True
    )
    chain = (
        load_prompt("skills_gap", required_variables={"profile", "criteria", "results"})
        | structured_model
    )
    response = chain.invoke(
        {"results": _format_results(results), "profile": profile_md, "criteria": criteria_md}
    )
    parsed = parse_structured_response(response, SkillsGapResponse)
    gaps = [SkillGap(**item.model_dump()) for item in parsed.gaps]
    logger.info(
        "skills_gap_complete",
        total_gaps=len(gaps),
        high=sum(1 for g in gaps if g.priority == "High"),
    )
    return gaps

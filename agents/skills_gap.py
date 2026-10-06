"""Skills Gap Agent — identifies and categorises missing skills across all matched jobs."""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from agents.model_client import create_chat_model
from agents.models import MatchResult, SkillGap
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

_SYSTEM = """\
You are a skills gap analysis agent. Given a list of job match results — each including \
the job title, company, and skills the user is missing — identify all distinct missing skills, \
categorise them, count how frequently each appears, and assign a priority.

Priority rules:
- "High": appears in ≥30% of jobs or is required by top-scoring jobs
- "Medium": appears in 10–29% of jobs
- "Low": appears in <10% of jobs

Return the analysis using the provided structured response schema.\
"""


_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "{results}"),
    ]
)


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


def run(results: list[MatchResult]) -> list[SkillGap]:
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
    chain = _PROMPT | structured_model
    response = chain.invoke({"results": _format_results(results)})
    # With include_raw=True, LangChain returns parsing errors instead of raising
    # them. Propagate them so invalid output cannot look like an empty analysis.
    if response["parsing_error"] is not None:
        raise response["parsing_error"]
    parsed = response["parsed"]
    if not isinstance(parsed, SkillsGapResponse):
        raise ValueError("Skills-gap model did not return the structured response")
    gaps = [SkillGap(**item.model_dump()) for item in parsed.gaps]
    logger.info(
        "skills_gap_complete",
        total_gaps=len(gaps),
        high=sum(1 for g in gaps if g.priority == "High"),
    )
    return gaps

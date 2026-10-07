"""Recommend improved search parameters; the coordinator owns state and file writes."""

from langchain_core.prompts import ChatPromptTemplate

from agents.model_client import create_chat_model
from agents.models import SearchGuidance, SearchSession
from config.search_guidance import normalize_locations
from config.settings import settings

_SYSTEM = """\
You are a search strategy advisor for a LinkedIn job search pipeline. \
Given the results of a profile matching session, your job is to recommend \
concrete improvements to the search parameters for the next iteration.

Analyse:
- Which jobs scored highly and what they have in common
- Which jobs scored poorly and why
- What keywords and experience-level filters might yield better results
- Which locations should be prioritised or added to broaden useful job discovery

The effective settings in the session context are authoritative. Do not propose \
changing the date filter, work modes, or job types. Configured locations are starting \
locations, not an allowlist. You may propose additional search regions such as Europe \
or EMEA when supported by the results and profile. Rank all proposed locations in \
priority order and explain any additions in your reasoning. Broader search regions \
do not change the user's geographic eligibility or preferences.

Return SearchGuidance using the supplied structured response schema. Include actionable \
keyword groups in priority order, supported experience levels (or an empty list for no \
filter), location priorities including useful new regions, session insights, and the reasoning for \
changes. The fixed settings still control the browser filters.\
"""


_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "{session_context}"),
    ]
)


def _format_session(session: SearchSession, prior_params: str, profile_md: str) -> str:
    strong = [m for m in session.matched_jobs if m.recommendation == "Strong Match"]
    good = [m for m in session.matched_jobs if m.recommendation == "Good Match"]
    weak = [m for m in session.matched_jobs if m.recommendation == "Weak Match"]
    skipped = [m for m in session.matched_jobs if m.recommendation == "Skip"]

    lines = [
        f"## Session Results — {session.timestamp}",
        f"Jobs scraped: {len(session.jobs_found)} | Matched: {len(session.matched_jobs)}",
        f"Strong matches: {len(strong)} | Good: {len(good)} | "
        f"Weak: {len(weak)} | Skip: {len(skipped)}",
        "",
    ]

    for heading, matches, limit in (
        ("Strong Matches", strong, 5),
        ("Good Matches", good, 3),
        ("Weak Matches", weak, 3),
        ("Skipped Jobs", skipped, 3),
    ):
        if matches:
            lines.append(f"### {heading}")
            for match in sorted(matches, key=lambda item: item.score, reverse=True)[:limit]:
                lines.append(
                    f"- {match.job.title} @ {match.job.company} "
                    f"(score {match.score:.0%}) — {match.match_reason}"
                )
            lines.append("")

    if session.skill_gaps:
        high_gaps = [gap for gap in session.skill_gaps if gap.priority == "High"]
        lines.append("### Top Missing Skills")
        for gap in high_gaps[:8]:
            lines.append(f"- {gap.skill} ({gap.category}, {gap.frequency} jobs)")
        lines.append("")

    lines += [
        "## Effective Settings (fixed)",
        f"Date filter: {settings.search_date_posted}",
        f"Work modes: {', '.join(settings.search_work_modes_list) or '(no filter)'}",
        f"Job types: {', '.join(settings.search_job_types_list) or '(no filter)'}",
        "",
        "## Starting Search Locations (expandable)",
        ", ".join(settings.search_locations_list) or "(none)",
        "Keywords, experience levels, and search locations are adjustable.",
        "New search regions do not change where the user can legally or practically take a role.",
        "",
        "## Current Search Parameters",
        prior_params,
        "",
        "## User Profile (summary context)",
        profile_md[:1500],
    ]

    return "\n".join(lines)


def run(session: SearchSession, prior_params: str, profile_md: str) -> SearchGuidance:
    """Return validated advice without saving files or changing the session."""
    model = create_chat_model(
        settings.orchestrator_model,
        max_tokens=2048,
        stage="refinement",
        tool_name=SearchGuidance.__name__,
    )
    chain = _PROMPT | model.with_structured_output(
        SearchGuidance, method="function_calling", include_raw=True
    )
    response = chain.invoke({"session_context": _format_session(session, prior_params, profile_md)})
    if response["parsing_error"] is not None:
        raise response["parsing_error"]
    guidance = response["parsed"]
    if not isinstance(guidance, SearchGuidance):
        raise ValueError("Refinement model did not return structured search guidance")
    return normalize_locations(guidance)

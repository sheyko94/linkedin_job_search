"""Recommend improved search parameters; the coordinator owns state and file writes."""

from langchain_core.prompts import ChatPromptTemplate

from agents.model_client import create_chat_model
from agents.models import SearchSession
from config.settings import settings

_SYSTEM = """\
You are a search strategy advisor for a LinkedIn job search pipeline. \
Given the results of a profile matching session, your job is to recommend \
concrete improvements to the search parameters for the next iteration.

Analyse:
- Which jobs scored highly and what they have in common
- Which jobs scored poorly and why
- What keywords and experience-level filters might yield better results
- Which configured locations should be prioritised

The effective settings in the session context are authoritative. Do not propose \
changing the date filter, work modes, job types, or configured location list. \
Adjust keywords and experience levels; location advice must use configured locations only.

Output a Markdown document for .state/search_params.md with:
1. A summary of insights from this session
2. Updated keywords, experience levels, and priorities among configured locations
3. What changed from the previous params and why

Be specific and actionable. The next search agent uses this document as guidance; \
the fixed settings still control the browser filters.\
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
        f"Configured locations: {', '.join(settings.search_locations_list) or '(none)'}",
        "Only keywords, experience levels, and priorities among these locations are adjustable.",
        "",
        "## Current Search Parameters",
        prior_params,
        "",
        "## User Profile (summary context)",
        profile_md[:1500],
    ]

    return "\n".join(lines)


def run(session: SearchSession, prior_params: str, profile_md: str) -> str:
    """Return Markdown for the next search without saving or changing the session."""
    model = create_chat_model(settings.orchestrator_model, max_tokens=2048, stage="refinement")
    chain = _PROMPT | model
    response = chain.invoke({"session_context": _format_session(session, prior_params, profile_md)})
    markdown = response.text
    if not markdown.strip():
        raise ValueError("Refinement model returned no search parameters")
    return markdown

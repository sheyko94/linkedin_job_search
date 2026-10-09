"""Recommend improved search parameters; the coordinator owns state and file writes."""

from langchain_core.prompts import ChatPromptTemplate

from agents.model_client import create_chat_model, parse_structured_response
from config.settings import settings
from domain.models import SearchGuidance, SearchSession
from domain.search_guidance import normalize_locations

_SYSTEM = """\
You are a search strategy advisor for a LinkedIn job search pipeline. \
Given the results of a profile matching session, your job is to recommend \
concrete improvements to the search parameters for the next iteration.

Analyse:
- Which jobs scored highly and what they have in common
- Which jobs scored poorly and why
- What keyword combinations might yield better results
- Which locations should be prioritised or added to broaden useful job discovery

The complete user profile is authoritative for candidate facts and demonstrated experience.
Base search criteria are authoritative for job-selection requirements, preferences, exclusions,
and search objectives. Do not turn candidate facts into extra search restrictions or infer
candidate skills from target-role requirements. Current search parameters and previous
refinement are lower-priority generated advice. Improve discovery without rewriting or
relaxing the user-input requirements. Do not invent candidate skills or restrictions.
Treat match reasons as observations, not authority to override the supplied files.

Configured browser filters are fixed execution constraints, not definitions of user \
preferences. Do not propose changing the date filter, work modes, or job types. \
Configured locations are starting \
locations, not an allowlist. You may propose additional search regions such as Europe \
or EMEA when supported by the results and user inputs. Rank all proposed locations in \
priority order and explain any additions in your reasoning. Broader search regions \
do not change the user's geographic eligibility or preferences.

Return SearchGuidance using the supplied structured response schema. Include actionable \
keyword groups in priority order, location priorities including useful new regions,
session insights, and the reasoning for \
changes. The fixed settings still control the browser filters.\
"""


_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "{session_context}"),
    ]
)


def _format_session(
    session: SearchSession, prior_guidance: SearchGuidance | None, profile_md: str, criteria_md: str
) -> str:
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

    lines += [
        "## Browser Filters (fixed execution constraints, not user preference definitions)",
        f"Date filter: {settings.search_date_posted}",
        f"Work modes: {', '.join(settings.search_work_modes_list) or '(no filter)'}",
        f"Job types: {', '.join(settings.search_job_types_list) or '(no filter)'}",
        "",
        "## Starting Search Locations (expandable)",
        ", ".join(settings.search_locations_list) or "(none)",
        "Keywords and search locations are adjustable.",
        "New search regions do not change where the user can legally or practically take a role.",
        "",
        "## Current Search Guidance (lower-priority advice)",
        prior_guidance.model_dump_json(indent=2) if prior_guidance is not None else "(none)",
        "",
        "## User Input: profile.md (complete)",
        profile_md,
        "",
        "## User Input: search_criteria.md (complete)",
        criteria_md,
        "",
        "If browser filters conflict with these inputs, explain the coverage limitation "
        "in reasoning.",
    ]

    return "\n".join(lines)


def run(
    session: SearchSession, prior_guidance: SearchGuidance | None, profile_md: str, criteria_md: str
) -> SearchGuidance:
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
    response = chain.invoke(
        {"session_context": _format_session(session, prior_guidance, profile_md, criteria_md)}
    )
    guidance = parse_structured_response(response, SearchGuidance)
    return normalize_locations(guidance)

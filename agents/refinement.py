"""Recommend improved search parameters; the coordinator owns state and file writes."""

from agents.model_client import create_chat_model, parse_structured_response
from config.settings import settings
from domain.models import SearchGuidance, SearchSession
from domain.search_guidance import normalize_locations
from prompts.prompt import load_prompt


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
        "## Browser Filters",
        f"Date filter: {settings.search_date_posted}",
        f"Work modes: {', '.join(settings.search_work_modes_list) or '(no filter)'}",
        f"Job types: {', '.join(settings.search_job_types_list) or '(no filter)'}",
        "",
        "## Starting Search Locations",
        ", ".join(settings.search_locations_list) or "(none)",
        "",
        "## Current Search Guidance",
        prior_guidance.model_dump_json(indent=2) if prior_guidance is not None else "(none)",
        "",
        "## User Input: profile.md (complete)",
        profile_md,
        "",
        "## User Input: search_criteria.md (complete)",
        criteria_md,
        "",
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
    chain = load_prompt(
        "refinement", required_variables={"session_context"}
    ) | model.with_structured_output(SearchGuidance, method="function_calling", include_raw=True)
    response = chain.invoke(
        {"session_context": _format_session(session, prior_guidance, profile_md, criteria_md)}
    )
    guidance = parse_structured_response(response, SearchGuidance)
    return normalize_locations(guidance)

"""Orchestrator — runs the LinkedIn job search pipeline and manages refinement
between iterations."""

import time
import uuid
from datetime import datetime

import structlog.contextvars

from agents import matcher, search, skills_gap
from agents.models import SearchSession
from config import reader, writer
from config.logging import get_logger
from config.settings import settings
from llm import anthropic as llm

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Refinement prompt — coordinator LLM decides how to improve next search
# ---------------------------------------------------------------------------

_REFINEMENT_SYSTEM = """\
You are a search strategy advisor for a LinkedIn job search pipeline. \
Given the results of a profile matching session, your job is to recommend \
concrete improvements to the search parameters for the next iteration.

Analyse:
- Which jobs scored highly and what they have in common
- Which jobs scored poorly and why
- What search terms, filters, or locations might yield better results

Output a Markdown document for .state/search_params.md with:
1. A summary of insights from this session
2. Updated search parameters (keywords, location, experience level, work mode, date filter)
3. What changed from the previous params and why

Be specific and actionable. The next search agent will use this document literally.\
"""


def _refinement_prompt(session: SearchSession, prior_params: str, profile_md: str) -> str:
    strong = [m for m in session.matched_jobs if m.recommendation == "Strong Match"]
    good = [m for m in session.matched_jobs if m.recommendation == "Good Match"]
    weak = [m for m in session.matched_jobs if m.recommendation in ("Weak Match", "Skip")]

    lines = [
        f"## Session Results — {session.timestamp}",
        f"Jobs scraped: {len(session.jobs_found)} | Matched: {len(session.matched_jobs)}",
        f"Strong matches: {len(strong)} | Good: {len(good)} | Weak/Skip: {len(weak)}",
        "",
    ]

    if strong:
        lines.append("### Strong Matches")
        for match in strong[:5]:
            lines.append(f"- {match.job.title} @ {match.job.company} — {match.match_reason}")
        lines.append("")

    if session.skill_gaps:
        high_gaps = [gap for gap in session.skill_gaps if gap.priority == "High"]
        lines.append("### Top Missing Skills")
        for gap in high_gaps[:8]:
            lines.append(f"- {gap.skill} ({gap.category}, {gap.frequency} jobs)")
        lines.append("")

    lines += [
        "## Current Search Parameters",
        prior_params,
        "",
        "## User Profile (summary context)",
        profile_md[:1500],
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run() -> SearchSession:
    session_id = str(uuid.uuid4())[:8]
    structlog.contextvars.bind_contextvars(session_id=session_id)
    start = time.monotonic()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    logger.info("coordinator_start", session_id=session_id)

    profile_md = reader.load_profile()
    criteria_md = reader.load_search_criteria()
    search_params_md = reader.load_search_params()

    # Bootstrap: if no prior search params, initialise from criteria
    if not search_params_md.strip():
        search_params_md = (
            f"# Search Parameters (auto-initialised from search_criteria.md)\n\n{criteria_md}"
        )
        writer.save_search_params(search_params_md)
        logger.info("coordinator_params_initialised_from_criteria")

    session = SearchSession(
        session_id=session_id,
        timestamp=now,
        search_params_used={},
    )

    deadline = start + settings.orchestrator_timeout

    for iteration in range(settings.max_refinement_iterations):
        if time.monotonic() > deadline:
            logger.warning("coordinator_timeout", iteration=iteration)
            break

        logger.info("coordinator_iteration_start", iteration=iteration + 1)

        # 1. Search
        refinement_hint = session.search_refinements[-1] if session.search_refinements else ""
        new_jobs = search.run(
            search_params_md=search_params_md,
            criteria_md=criteria_md,
            refinement_hint=refinement_hint,
        )

        # Deduplicate against prior iterations
        seen_ids = {j.id for j in session.jobs_found}
        unique_new = [j for j in new_jobs if j.id not in seen_ids]
        session.jobs_found.extend(unique_new)
        logger.info(
            "coordinator_search_done", new_jobs=len(unique_new), total=len(session.jobs_found)
        )

        if not unique_new:
            logger.info("coordinator_no_new_jobs_stopping")
            break

        # 2. Match
        new_matches = matcher.run(unique_new, profile_md)
        session.matched_jobs.extend(new_matches)
        logger.info("coordinator_matching_done", matched=len(new_matches))

        # 3. Refine search params for next iteration (skip on last iteration)
        if iteration < settings.max_refinement_iterations - 1:
            if time.monotonic() > deadline:
                break
            refined_params = llm.complete(
                system=_REFINEMENT_SYSTEM,
                user=_refinement_prompt(session, search_params_md, profile_md),
                model=settings.orchestrator_model,
                max_tokens=2048,
            )
            search_params_md = refined_params
            writer.save_search_params(refined_params)
            logger.info("coordinator_params_refined")

            # Extract refinement hint for next search agent call
            session.search_refinements.append(
                f"Iteration {iteration + 1} refinement applied — see .state/search_params.md"
            )

    # 4. Skills gap analysis across all sessions
    session.skill_gaps = skills_gap.run(session.matched_jobs)
    logger.info("coordinator_skills_gap_done", gaps=len(session.skill_gaps))

    # 5. Persist outputs
    writer.save_matched_jobs(session)
    writer.save_skills_gap(session.skill_gaps, session_id)

    total_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "coordinator_complete",
        session_id=session_id,
        total_jobs=len(session.jobs_found),
        total_matched=len(session.matched_jobs),
        total_gaps=len(session.skill_gaps),
        latency_ms=total_ms,
    )

    structlog.contextvars.clear_contextvars()
    return session

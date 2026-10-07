"""LangGraph workflow for search, matching, refinement, and reporting."""

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import structlog.contextvars
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents import matcher, refinement, search, skills_gap
from agents.models import JobPosting, MatchResult, SearchGuidance, SearchSession, SkillGap
from config import reader, writer
from config.logging import configure, get_logger
from config.search_guidance import (
    effective_locations,
    normalize_locations,
    parse_markdown,
    render_markdown,
)
from config.settings import settings

logger = get_logger(__name__)


class PipelineState(TypedDict):
    """Workflow data. Nodes return partial updates; other fields remain unchanged.

    Lists use LangGraph's default replacement behavior. Each accumulating node
    returns a new complete list, so no append reducers are needed in this graph.
    """

    session_id: str
    timestamp: str
    output_dir: str
    profile_md: str
    criteria_md: str
    search_params_md: str
    search_guidance: SearchGuidance | None
    search_params_used: dict
    iteration: int  # Number of searches started, initially zero.
    deadline: float  # Monotonic time; only valid within this process.
    new_jobs: list[JobPosting]
    jobs_found: list[JobPosting]
    matched_jobs: list[MatchResult]
    skill_gaps: list[SkillGap]
    search_refinements: list[str]


def _to_session(state: PipelineState) -> SearchSession:
    """Adapt graph state to the existing report and terminal display contract."""
    return SearchSession(
        session_id=state["session_id"],
        timestamp=state["timestamp"],
        output_dir=state["output_dir"],
        search_params_used=state["search_params_used"],
        jobs_found=state["jobs_found"],
        matched_jobs=state["matched_jobs"],
        skill_gaps=state["skill_gaps"],
        search_refinements=state["search_refinements"],
    )


def _load_inputs(state: PipelineState) -> dict:
    profile_md = reader.load_profile()
    criteria_md = reader.load_search_criteria()
    search_params_md = reader.load_search_params()
    if not search_params_md.strip():
        search_params_md = (
            f"# Search Parameters (auto-initialised from search_criteria.md)\n\n{criteria_md}"
        )
        writer.save_search_params(search_params_md)
        logger.info("coordinator_params_initialised_from_criteria")
    guidance = parse_markdown(search_params_md)
    if guidance is not None:
        guidance = normalize_locations(guidance)
    return {
        "profile_md": profile_md,
        "criteria_md": criteria_md,
        "search_params_md": search_params_md,
        "search_guidance": guidance,
    }


def _can_search(state: PipelineState) -> bool:
    if state["iteration"] >= settings.max_refinement_iterations:
        return False
    if time.monotonic() > state["deadline"]:
        logger.warning("coordinator_timeout", iteration=state["iteration"])
        return False
    return True


def _route_after_load(state: PipelineState) -> Literal["search", "analyze_gaps"]:
    return "search" if _can_search(state) else "analyze_gaps"


def _search_jobs(state: PipelineState) -> dict:
    iteration = state["iteration"] + 1
    logger.info("coordinator_iteration_start", iteration=iteration)
    refinements = state["search_refinements"]
    refinement_hint = refinements[-1] if refinements else ""
    snapshot = {
        "iteration": iteration,
        "search_params_md": state["search_params_md"],
        "criteria_md": state["criteria_md"],
        "refinement_hint": refinement_hint,
        "search_guidance": state["search_guidance"].model_dump()
        if state["search_guidance"] is not None
        else None,
        "effective_settings": {
            "starting_locations": settings.search_locations_list,
            "locations": effective_locations(
                state["search_guidance"], settings.search_locations_list
            ),
            "date_posted": settings.search_date_posted,
            "work_modes": settings.search_work_modes_list,
            "job_types": settings.search_job_types_list,
            "max_jobs_per_search": settings.max_jobs_per_search,
            "max_total_jobs": settings.max_total_jobs,
        },
    }
    new_jobs = search.run(
        search_params_md=state["search_params_md"],
        criteria_md=state["criteria_md"],
        refinement_hint=refinement_hint,
        guidance=state["search_guidance"],
        previous_job_ids=frozenset(job.id for job in state["jobs_found"]),
    )
    return {
        "new_jobs": new_jobs,
        "iteration": iteration,
        "search_params_used": {
            **state["search_params_used"],
            "iterations": state["search_params_used"]["iterations"] + [snapshot],
        },
    }


def _deduplicate_jobs(state: PipelineState) -> dict:
    # Search already deduplicates within an iteration; this filters prior iterations.
    seen_ids = {job.id for job in state["jobs_found"]}
    unique_new = [job for job in state["new_jobs"] if job.id not in seen_ids]
    jobs_found = state["jobs_found"] + unique_new
    logger.info("coordinator_search_done", new_jobs=len(unique_new), total=len(jobs_found))
    return {"new_jobs": unique_new, "jobs_found": jobs_found}


def _route_after_deduplication(state: PipelineState) -> Literal["match", "analyze_gaps"]:
    if state["new_jobs"]:
        return "match"
    logger.info("coordinator_no_new_jobs_stopping")
    return "analyze_gaps"


def _match_jobs(state: PipelineState) -> dict:
    new_matches = matcher.run(state["new_jobs"], state["profile_md"])
    logger.info("coordinator_matching_done", matched=len(new_matches))
    return {"matched_jobs": state["matched_jobs"] + new_matches}


def _route_after_matching(state: PipelineState) -> Literal["refine", "analyze_gaps"]:
    return "refine" if _can_search(state) else "analyze_gaps"


def _refine_params(state: PipelineState) -> dict:
    guidance = refinement.run(
        session=_to_session(state),
        prior_params=state["search_params_md"],
        profile_md=state["profile_md"],
    )
    refined_params = render_markdown(guidance)
    writer.save_search_params(refined_params)
    logger.info("coordinator_params_refined")
    hint = f"Iteration {state['iteration']} refinement applied — see .state/search_params.md"
    return {
        "search_params_md": refined_params,
        "search_guidance": guidance,
        "search_refinements": state["search_refinements"] + [hint],
    }


def _analyze_gaps(state: PipelineState) -> dict:
    gaps = skills_gap.run(state["matched_jobs"])
    logger.info("coordinator_skills_gap_done", gaps=len(gaps))
    return {"skill_gaps": gaps}


def _persist_reports(state: PipelineState) -> dict:
    session = _to_session(state)
    writer.save_matched_jobs(session)
    writer.save_skills_gap(session)
    return {}


def build_graph() -> CompiledStateGraph:
    """Declare the workflow. This first migration has no checkpointer or retries."""
    graph = StateGraph(PipelineState)
    graph.add_node("load_inputs", _load_inputs)
    graph.add_node("search", _search_jobs)
    graph.add_node("deduplicate", _deduplicate_jobs)
    graph.add_node("match", _match_jobs)
    graph.add_node("refine", _refine_params)
    graph.add_node("analyze_gaps", _analyze_gaps)
    graph.add_node("persist", _persist_reports)

    graph.add_edge(START, "load_inputs")
    graph.add_conditional_edges("load_inputs", _route_after_load)
    graph.add_edge("search", "deduplicate")
    graph.add_conditional_edges("deduplicate", _route_after_deduplication)
    graph.add_conditional_edges("match", _route_after_matching)
    # Refinement can consume the remaining time: check again before searching.
    graph.add_conditional_edges("refine", _route_after_load)
    graph.add_edge("analyze_gaps", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def run(on_stage: Callable[[str], None] | None = None) -> SearchSession:
    """Run the graph, optionally reporting node starts without exposing state."""
    session_id = str(uuid.uuid4())[:8]
    started_at = datetime.now().astimezone()
    output_dir = Path(settings.output_dir) / (
        f"{started_at.strftime('%Y-%m-%d_%H-%M-%S-%f')}_{session_id}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    configure(output_dir / "execution_trace.log", started_at)
    structlog.contextvars.bind_contextvars(session_id=session_id)
    start = time.monotonic()
    logger.info("coordinator_start", session_id=session_id, output_dir=str(output_dir))
    initial_state: PipelineState = {
        "session_id": session_id,
        "timestamp": started_at.isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "profile_md": "",
        "criteria_md": "",
        "search_params_md": "",
        "search_guidance": None,
        "search_params_used": {"iterations": []},
        "iteration": 0,
        "deadline": start + settings.orchestrator_timeout,
        "new_jobs": [],
        "jobs_found": [],
        "matched_jobs": [],
        "skill_gaps": [],
        "search_refinements": [],
    }
    try:
        # Graph steps are not search iterations. Allow enough steps for the entire
        # configured loop plus initialization and final reporting.
        state = initial_state
        for mode, event in build_graph().stream(
            initial_state,
            config={"recursion_limit": max(10, settings.max_refinement_iterations * 5 + 5)},
            stream_mode=["tasks", "values"],
        ):
            if mode == "tasks" and "input" in event:
                # Task-start events contain input; completion events contain result.
                # Send only the node name to the UI, never profiles or descriptions.
                if on_stage is not None:
                    on_stage(event["name"])
            elif mode == "values":
                state = event
        session = _to_session(state)
        logger.info(
            "coordinator_complete",
            session_id=session_id,
            total_jobs=len(session.jobs_found),
            total_matched=len(session.matched_jobs),
            total_gaps=len(session.skill_gaps),
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return session
    finally:
        structlog.contextvars.clear_contextvars()

"""LangGraph workflow for search, matching, refinement, and reporting."""

import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import structlog.contextvars
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents import matcher, refinement, search, skills_gap
from config.settings import settings
from domain.models import (
    JobPosting,
    MatchResult,
    SearchGuidance,
    SearchSession,
    SearchSnapshot,
    SkillGap,
)
from domain.search_guidance import (
    effective_locations,
    normalize_locations,
)
from observability.logging import configure, get_logger, reset_trace
from storage import reader, writer

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
    discard_keywords: str
    search_guidance: SearchGuidance | None
    search_history: list[SearchSnapshot]
    iteration: int  # Number of searches started, initially zero.
    deadline: float  # Monotonic time; only valid within this process.
    new_jobs: list[JobPosting]
    jobs_found: list[JobPosting]
    matched_jobs: list[MatchResult]
    skill_gaps: list[SkillGap]
    search_refinements: list[SearchGuidance]


def _to_session(state: PipelineState) -> SearchSession:
    """Adapt graph state to the existing report and terminal display contract."""
    return SearchSession(
        session_id=state["session_id"],
        timestamp=state["timestamp"],
        output_dir=state["output_dir"],
        search_history=state["search_history"],
        jobs_found=state["jobs_found"],
        matched_jobs=state["matched_jobs"],
        skill_gaps=state["skill_gaps"],
        search_refinements=state["search_refinements"],
    )


def _load_inputs(state: PipelineState) -> dict:
    get_stream_writer()({"kind": "stage", "stage": "load_inputs"})
    profile_md = reader.load_profile()
    criteria_md = reader.load_search_criteria()
    guidance = reader.load_search_guidance()
    if guidance is not None:
        guidance = normalize_locations(guidance)
    return {
        "profile_md": profile_md,
        "criteria_md": criteria_md,
        "discard_keywords": ", ".join(sorted(reader.load_discard_keywords())),
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
    get_stream_writer()({"kind": "stage", "stage": "search"})
    iteration = state["iteration"] + 1
    logger.info("coordinator_iteration_start", iteration=iteration)
    snapshot = SearchSnapshot(
        iteration=iteration,
        criteria_md=state["criteria_md"],
        guidance=state["search_guidance"],
        starting_locations=settings.search_locations_list,
        locations=effective_locations(state["search_guidance"], settings.search_locations_list),
        date_posted=settings.search_date_posted,
        work_modes=settings.search_work_modes_list,
        job_types=settings.search_job_types_list,
        max_jobs_per_search=settings.max_jobs_per_search,
        max_total_jobs=settings.max_total_jobs,
    )
    new_jobs = search.run(
        criteria_md=state["criteria_md"],
        profile_md=state["profile_md"],
        discard_keywords=state["discard_keywords"],
        guidance=state["search_guidance"],
        previous_job_ids=frozenset(job.id for job in state["jobs_found"]),
    )
    return {
        "new_jobs": new_jobs,
        "iteration": iteration,
        "search_history": state["search_history"] + [snapshot],
    }


def _deduplicate_jobs(state: PipelineState) -> dict:
    get_stream_writer()({"kind": "stage", "stage": "deduplicate"})
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
    get_stream_writer()({"kind": "stage", "stage": "match"})
    new_matches = matcher.run(
        state["new_jobs"], state["profile_md"], state["criteria_md"], state["discard_keywords"]
    )
    logger.info("coordinator_matching_done", matched=len(new_matches))
    return {"matched_jobs": state["matched_jobs"] + new_matches}


def _route_after_matching(state: PipelineState) -> Literal["refine", "analyze_gaps"]:
    return "refine" if _can_search(state) else "analyze_gaps"


def _refine_params(state: PipelineState) -> dict:
    get_stream_writer()({"kind": "stage", "stage": "refine"})
    guidance = refinement.run(
        session=_to_session(state),
        prior_guidance=state["search_guidance"],
        profile_md=state["profile_md"],
        criteria_md=state["criteria_md"],
    )
    writer.save_search_guidance(guidance)
    logger.info("coordinator_params_refined")
    return {
        "search_guidance": guidance,
        "search_refinements": state["search_refinements"] + [guidance],
    }


def _analyze_gaps(state: PipelineState) -> dict:
    get_stream_writer()({"kind": "stage", "stage": "analyze_gaps"})
    gaps = skills_gap.run(state["matched_jobs"], state["profile_md"], state["criteria_md"])
    logger.info("coordinator_skills_gap_done", gaps=len(gaps))
    return {"skill_gaps": gaps}


def _persist_reports(state: PipelineState) -> dict:
    get_stream_writer()({"kind": "stage", "stage": "persist"})
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


def run(
    on_stage: Callable[[str], None] | None = None,
    on_progress: Callable[[dict], None] | None = None,
) -> SearchSession:
    """Run the graph and expose only explicit progress events to the UI."""
    session_id = str(uuid.uuid4())[:8]
    started_at = datetime.now().astimezone()
    output_dir = Path(settings.output_dir) / (
        f"{started_at.strftime('%Y-%m-%d_%H-%M-%S-%f')}_{session_id}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    trace_token = configure(output_dir / "execution_trace.log", started_at)
    log_tokens = structlog.contextvars.bind_contextvars(session_id=session_id)
    start = time.monotonic()
    logger.info("coordinator_start", session_id=session_id, output_dir=str(output_dir))
    initial_state: PipelineState = {
        "session_id": session_id,
        "timestamp": started_at.isoformat(timespec="seconds"),
        "output_dir": str(output_dir),
        "profile_md": "",
        "criteria_md": "",
        "discard_keywords": "",
        "search_guidance": None,
        "search_history": [],
        "iteration": 0,
        "deadline": start + settings.orchestrator_timeout,
        "new_jobs": [],
        "jobs_found": [],
        "matched_jobs": [],
        "skill_gaps": [],
        "search_refinements": [],
    }
    usage = UsageMetadataCallbackHandler()
    completed = False
    try:
        # Graph steps are not search iterations. Allow enough steps for the entire
        # configured loop plus initialization and final reporting.
        state = initial_state
        for part in build_graph().stream(
            initial_state,
            config={
                "recursion_limit": max(10, settings.max_refinement_iterations * 5 + 5),
                "callbacks": [usage],
            },
            stream_mode=["custom", "values"],
            subgraphs=True,
            version="v2",
        ):
            if part["type"] == "custom":
                event = part["data"]
                if event.get("kind") == "stage" and on_stage is not None:
                    on_stage(event["stage"])
                elif on_progress is not None:
                    on_progress(event)
            elif part["type"] == "values" and not part["ns"]:
                state = part["data"]
        session = _to_session(state)
        session.token_usage = dict(usage.usage_metadata)
        logger.info(
            "coordinator_complete",
            session_id=session_id,
            total_jobs=len(session.jobs_found),
            total_matched=len(session.matched_jobs),
            total_gaps=len(session.skill_gaps),
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        completed = True
        return session
    finally:
        # Persist provider-reported usage even when a later stage fails.
        try:
            try:
                writer.save_token_usage(output_dir, usage.usage_metadata, completed=completed)
            except OSError as exc:
                logger.warning("token_usage_save_failed", error=str(exc))
        finally:
            reset_trace(trace_token)
            structlog.contextvars.reset_contextvars(**log_tokens)

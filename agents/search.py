"""Job Search Agent — reads search params, drives LinkedIn browser scraping via tools."""

import math
import time
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.types import Command

from agents.model_client import create_chat_model
from agents.models import JobPosting
from config.logging import get_logger, trace_payload
from config.reader import load_discard_keywords
from config.settings import settings
from tools import linkedin
from tools.browser_session import BrowserSession, LinkedInAuthenticationError
from tools.search_context import SearchContext
from tools.search_tools import SEARCH_TOOLS, apply_job_details

logger = get_logger(__name__)


_MAX_MODEL_CALLS = 15


_SYSTEM = """\
You are a LinkedIn job search agent. Your job is to search for and collect job listings \
that match the provided search parameters. You have two tools:

- scrape_jobs: search LinkedIn with keywords, location, and filters
- get_job_details: fetch the full description for a specific job URL

Strategy:
1. Call scrape_jobs with the most relevant keyword combination from the parameters.
2. If the parameters include multiple keyword groups or locations, call scrape_jobs \
again with variations.
3. Use get_job_details only for jobs where the card info is insufficient to evaluate the role.
4. When you have collected enough jobs (aim for the requested max), stop and summarise \
what you found.

Never invent job data. Only report what the browser returns.\
"""


_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        MessagesPlaceholder("messages"),
    ]
)


def _format_search_params(search_params_md: str, criteria_md: str) -> str:
    locations = ", ".join(settings.search_locations_list)
    return (
        f"## Current Search Parameters\n{search_params_md}\n\n"
        f"## Base Search Criteria\n{criteria_md}\n\n"
        f"Locations to search (call scrape_jobs once per location): {locations}\n"
        f"Max jobs per search call: {settings.max_jobs_per_search}\n"
        f"Max total jobs to collect across all calls: {settings.max_total_jobs}\n"
        "Stop calling scrape_jobs once you reach the total limit.\n"
        "Use the tools to search LinkedIn and collect job listings now."
    )


class SearchState(TypedDict):
    """Local agent conversation and collected jobs; no browser objects are stored here."""

    messages: Annotated[list[AnyMessage], add_messages]
    jobs_by_id: dict[str, JobPosting]
    scrape_calls: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    stop_reason: str


def _budget_reached(state: SearchState) -> bool:
    max_calls = math.ceil(settings.max_total_jobs / settings.max_jobs_per_search)
    return state["scrape_calls"] >= max_calls or len(state["jobs_by_id"]) >= settings.max_total_jobs


def build_search_graph() -> CompiledStateGraph:
    """Build the graph independently of the browser supplied at invocation time."""
    model = create_chat_model(settings.search_model, max_tokens=2048, stage="search").bind_tools(
        SEARCH_TOOLS, parallel_tool_calls=False
    )
    chain = _PROMPT | model
    tool_node = ToolNode(SEARCH_TOOLS)

    def call_model(state: SearchState) -> dict:
        response = chain.invoke({"messages": state["messages"]})
        usage = response.usage_metadata or {}
        return {
            "messages": [response],
            "model_calls": state["model_calls"] + 1,
            "input_tokens": state["input_tokens"] + usage.get("input_tokens", 0),
            "output_tokens": state["output_tokens"] + usage.get("output_tokens", 0),
        }

    def execute_tools(
        state: SearchState, config: RunnableConfig, runtime: Runtime[SearchContext]
    ) -> dict:
        # ToolNode handles dispatch, validation, runtime injection and replies.
        # One call at a time gives the next call the previous call's state updates.
        jobs = state["jobs_by_id"]
        scrape_calls = state["scrape_calls"]
        messages: list[ToolMessage] = []
        response = state["messages"][-1]
        for call in response.tool_calls:
            trace_payload(f"{call['name']} -> LLM tool input (verbatim)", call["args"])
            call_state = {
                **state,
                "jobs_by_id": jobs,
                "scrape_calls": scrape_calls,
                "messages": [response.model_copy(update={"tool_calls": [call]})],
            }
            result = tool_node.invoke(call_state, config=config, runtime=runtime)
            # Successful tools return Commands; validation/unknown-tool replies
            # return a messages dict. Only these tools' state fields are combined.
            for output in result if isinstance(result, list) else [result]:
                update = output.update if isinstance(output, Command) else output
                jobs = update.get("jobs_by_id", jobs)
                scrape_calls = update.get("scrape_calls", scrape_calls)
                for reply in update["messages"]:
                    trace_payload(f"{call['name']} <- tool result (verbatim)", reply.content)
                    messages.append(reply)
        return {"messages": messages, "jobs_by_id": jobs, "scrape_calls": scrape_calls}

    def route_after_model(state: SearchState) -> Literal["tools", "enrich"]:
        response = state["messages"][-1]
        return "tools" if isinstance(response, AIMessage) and response.tool_calls else "enrich"

    def route_after_tools(state: SearchState) -> Literal["model", "enrich"]:
        if _budget_reached(state) or state["model_calls"] >= _MAX_MODEL_CALLS:
            return "enrich"
        return "model"

    def enrich(state: SearchState, runtime: Runtime[SearchContext]) -> dict:
        if _budget_reached(state):
            stop_reason = "search_budget"
            logger.info("search_job_limit_reached", total=len(state["jobs_by_id"]))
        elif state["model_calls"] >= _MAX_MODEL_CALLS:
            stop_reason = "model_call_limit"
            logger.warning("search_model_call_limit_reached", max_iterations=_MAX_MODEL_CALLS)
        else:
            stop_reason = "model_finished"
        jobs = {job_id: job.model_copy(deep=True) for job_id, job in state["jobs_by_id"].items()}
        runtime.context.browser.call(_enrich_jobs, jobs)
        return {"jobs_by_id": jobs, "stop_reason": stop_reason}

    graph = StateGraph(SearchState, context_schema=SearchContext)
    graph.add_node("model", call_model)
    graph.add_node("tools", execute_tools)
    graph.add_node("enrich", enrich)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", route_after_model)
    graph.add_conditional_edges("tools", route_after_tools)
    graph.add_edge("enrich", END)
    return graph.compile()


def run(
    search_params_md: str,
    criteria_md: str,
    refinement_hint: str = "",
) -> list[JobPosting]:
    """Open runtime browser resources, invoke the subgraph, return actual scraped jobs."""
    user_prompt = _format_search_params(search_params_md, criteria_md)
    if refinement_hint:
        user_prompt += f"\n\nRefinement guidance from prior session:\n{refinement_hint}"
    initial_state: SearchState = {
        "messages": [HumanMessage(content=user_prompt)],
        "jobs_by_id": {},
        "scrape_calls": 0,
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "stop_reason": "",
    }
    start = time.monotonic()
    with BrowserSession() as browser:
        if not browser.logged_in:
            logger.error("linkedin_login_failed")
            raise LinkedInAuthenticationError("Could not sign in to LinkedIn.")
        state = build_search_graph().invoke(
            initial_state,
            config={"recursion_limit": _MAX_MODEL_CALLS * 2 + 5},
            context=SearchContext(browser=browser),
        )
    result = list(state["jobs_by_id"].values())
    logger.info(
        "llm_search_graph",
        model=settings.search_model,
        total_input_tokens=state["input_tokens"],
        total_output_tokens=state["output_tokens"],
        model_calls=state["model_calls"],
        scrape_calls=state["scrape_calls"],
        stop_reason=state["stop_reason"],
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    logger.info("search_agent_complete", total_jobs=len(result))
    return result


def _is_obvious_discard(job: JobPosting, keywords: set[str]) -> bool:
    title_lower = job.title.lower()
    return any(kw in title_lower for kw in keywords)


def _enrich_jobs(page: Any, jobs_by_id: dict[str, JobPosting]) -> None:
    keywords = load_discard_keywords()
    # A populated description marks a successful prior tool fetch. Failed or
    # incomplete fetches leave it empty, so those jobs remain eligible for retry.
    to_fetch = [
        job
        for job in jobs_by_id.values()
        if not job.description.strip() and not _is_obvious_discard(job, keywords)
    ]
    logger.info("search_enriching_jobs", total=len(to_fetch))
    for job in to_fetch:
        try:
            time.sleep(settings.job_detail_delay_ms / 1000)
            details = linkedin.get_job_details(page, job.url)
            apply_job_details(job, details)
        except Exception as e:
            logger.warning("search_enrich_failed", job_id=job.id, error=str(e))

"""Orchestrator agent — decides when to research and when to answer, never retrieves or synthesises directly."""

import time
import uuid

import structlog.contextvars

from agents import answer, research
from agents.models import AnswerResult, QueryResult
from config.logging import get_logger
from config.settings import settings
from llm import client as llm
from mcp.client import MCPClient
from opensearch.models import RetrievalResult
from opensearch.reranker import rerank

logger = get_logger(__name__)


def _system_prompt(max_attempts: int) -> str:
    return (
        "You are an orchestrator agent coordinating a RAG pipeline. You have two tools:\n"
        "- run_research: searches the knowledge base and accumulates evidence chunks.\n"
        "- generate_answer: synthesises all collected evidence into a grounded answer.\n\n"
        "Rules:\n"
        "1. Always call run_research at least once before generate_answer.\n"
        "2. After generate_answer, if missing_information is true or confidence is low, call run_research again "
        "with the identified gaps, then call generate_answer again.\n"
        f"3. You may call generate_answer at most {max_attempts} time(s). Stop as soon as the answer is confident and complete.\n"
        "4. Your final tool call must always be generate_answer."
    )


def run(query: str) -> QueryResult:
    trace_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(trace_id=trace_id)

    start = time.monotonic()
    deadline = start + settings.orchestrator_timeout
    retrieval_result: RetrievalResult = RetrievalResult(chunks=[])
    execution_result: AnswerResult | None = None
    attempts = 0

    logger.info("coordinator_start", query=query)

    def on_tool_call(name: str, input: dict) -> str:
        nonlocal retrieval_result, execution_result, attempts

        if time.monotonic() > deadline:
            raise TimeoutError(f"Orchestrator exceeded {settings.orchestrator_timeout}s wall-clock timeout.")

        if name == "run_research":
            gaps = input.get("gaps")
            t = time.monotonic()
            result = research.run(query, gaps=gaps)
            seen = {c.chunk_id for c in retrieval_result.chunks}
            new_chunks = [c for c in result.chunks if c.chunk_id not in seen]
            retrieval_result = RetrievalResult(chunks=retrieval_result.chunks + new_chunks)
            logger.info("coordinator_research_done",
                        total_chunks=len(retrieval_result.chunks),
                        latency_ms=int((time.monotonic() - t) * 1000))
            return f"Research complete. {len(retrieval_result.chunks)} chunks collected total."

        if name == "generate_answer":
            if attempts >= settings.max_attempts:
                return f"Max attempts ({settings.max_attempts}) reached. Stop now."
            attempts += 1
            chunks = rerank(query, retrieval_result.chunks) if settings.reranker_enabled else retrieval_result.chunks
            t = time.monotonic()
            execution_result = answer.run(query, RetrievalResult(chunks=chunks))
            logger.info(
                "coordinator_answer_done",
                attempt=attempts,
                confidence=execution_result.confidence,
                missing_information=execution_result.missing_information,
                latency_ms=int((time.monotonic() - t) * 1000),
            )
            status = f"confidence={execution_result.confidence:.2f}, missing_information={execution_result.missing_information}"
            if execution_result.notes:
                status += f", notes={execution_result.notes}"
            return status

        return "Unknown tool"

    llm.complete_with_tools(
        system=_system_prompt(settings.max_attempts),
        user=query,
        model=settings.orchestrator_model,
        tools=MCPClient().list_orchestrator_tools(),
        on_tool_call=on_tool_call,
    )

    if execution_result is None:
        execution_result = answer.run(query, retrieval_result)

    latency_ms = int((time.monotonic() - start) * 1000)
    logger.info("coordinator_complete", latency_ms=latency_ms, attempts=attempts, confidence=execution_result.confidence)

    structlog.contextvars.clear_contextvars()

    return QueryResult(
        query=query,
        retrieval=retrieval_result,
        execution=execution_result,
        total_latency_ms=latency_ms,
    )

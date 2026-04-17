import time

from agents import answer, research
from agents.models import OrchestratedResult, UserTask
from config.logging import get_logger

logger = get_logger(__name__)


def run(query: str) -> OrchestratedResult:
    task = UserTask(query=query)
    start = time.monotonic()

    logger.info("coordinator_start", query=query)

    retrieval_result = research.run(task)
    execution_result = answer.run(task, retrieval_result)

    latency_ms = int((time.monotonic() - start) * 1000)
    logger.info("coordinator_complete", latency_ms=latency_ms, confidence=execution_result.confidence)

    return OrchestratedResult(
        query=query,
        retrieval=retrieval_result,
        execution=execution_result,
        total_latency_ms=latency_ms,
    )

"""Answer agent — synthesises retrieved evidence, never retrieves."""

from agents.models import ExecutionResult, UserTask
from search.models import RetrievalResult
from llm import client as llm
from llm.parser import parse_execution_result
from llm.prompts import EXECUTOR_SYSTEM, executor_user
from config.logging import get_logger

logger = get_logger(__name__)


def run(task: UserTask, retrieval: RetrievalResult) -> ExecutionResult:
    if not retrieval.chunks:
        logger.warning("answer_agent_no_evidence", query=task.query)
        return ExecutionResult(
            answer="No relevant information was found in the knowledge base.",
            citations=[],
            confidence=0.0,
            missing_information=True,
            notes="Retrieval returned zero chunks.",
        )

    user_msg = executor_user(task.query, retrieval.chunks)
    raw = llm.complete(system=EXECUTOR_SYSTEM, user=user_msg)
    logger.info("answer_agent_llm_response", raw=raw)

    result = parse_execution_result(raw)
    logger.info(
        "answer_agent_complete",
        confidence=result.confidence,
        citations=result.citations,
        missing_information=result.missing_information,
    )
    return result

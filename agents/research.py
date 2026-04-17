"""Research agent — drives MCP tool calls, never answers."""

from config.settings import settings
from agents.models import UserTask
from search.models import RetrievedChunk, RetrievalResult
from llm import client as llm
from llm.prompts import RESEARCH_AGENT_SYSTEM
from mcp.client import MCPClient
from config.logging import get_logger
from search.client import search

logger = get_logger(__name__)


def run(task: UserTask) -> RetrievalResult:
    mcp = MCPClient()
    chunks: list[RetrievedChunk] = []
    seen: set[str] = set()

    def on_tool_call(_name: str, input: dict) -> str:
        results = search(input["query"], top_k=settings.retrieval_top_k)
        for c in results:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                chunks.append(c)
        logger.info("research_agent_search", query=input["query"], results=len(results))
        return "\n\n".join(f"[{c.chunk_id}] {c.text}" for c in results)

    llm.run_agent(
        system=RESEARCH_AGENT_SYSTEM,
        user=task.query,
        tools=mcp.list_tools(),
        on_tool_call=on_tool_call,
    )

    logger.info("research_agent_complete", total_chunks=len(chunks))
    return RetrievalResult(chunks=chunks)

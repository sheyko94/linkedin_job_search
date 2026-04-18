"""Research agent — drives MCP tool calls, never answers."""

from config.settings import settings
from opensearch.models import RetrievedChunk, RetrievalResult
from llm import client as llm
from mcp.client import MCPClient
from config.logging import get_logger
from opensearch.client import search

logger = get_logger(__name__)

_SYSTEM = """\
You are a research agent. Your only job is to gather evidence from the knowledge base \
to answer a user query. Call the search tool as many times as needed with different \
queries to collect enough evidence. When you have sufficient evidence, write a brief \
summary of what you found. Never answer the user's question directly — only report \
what the evidence says.\
"""


def _user_prompt(query: str, gaps: str | None = None) -> str:
    msg = query
    if gaps:
        msg += f"\n\nA previous answer attempt identified these gaps — search specifically for this missing information:\n{gaps}"
    return msg


def run(query: str, gaps: str | None = None) -> RetrievalResult:
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

    llm.complete_with_tools(
        system=_SYSTEM,
        user=_user_prompt(query, gaps),
        model=settings.research_model,
        tools=mcp.list_research_tools(),
        on_tool_call=on_tool_call,
        max_iterations=settings.max_search_iterations,
    )

    logger.info("research_agent_complete", total_chunks=len(chunks))
    return RetrievalResult(chunks=chunks)

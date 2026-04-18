from opensearch.client import search

_ORCHESTRATOR_TOOLS = [
    {
        "name": "run_research",
        "description": "Search the knowledge base to gather evidence. Call this first, and again with gaps if the answer is incomplete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gaps": {
                    "type": "string",
                    "description": "Specific missing information identified by a previous answer attempt. Omit on first call.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "generate_answer",
        "description": "Synthesise all collected evidence into a grounded answer. Returns confidence and whether information is missing.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

_RESEARCH_TOOLS = [
    {
        "name": "search",
        "description": "Search the knowledge base for relevant chunks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
    }
]


class MCPClient:
    """MCP client interface. Currently backed by local tools.
    To wire against a real MCP server, replace list_tools methods
    with calls to the MCP transport (e.g. via the `mcp` SDK).
    """

    def list_orchestrator_tools(self) -> list[dict]:
        # TODO: replace with mcp_session.list_tools() against a real server
        return _ORCHESTRATOR_TOOLS

    def list_research_tools(self) -> list[dict]:
        # TODO: replace with mcp_session.list_tools() against a real server
        return _RESEARCH_TOOLS

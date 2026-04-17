from search.client import search


class MCPClient:
    """MCP client interface. Currently backed by local tools.
    To wire against a real MCP server, replace list_tools and call_tool
    with calls to the MCP transport (e.g. via the `mcp` SDK).
    """

    def list_tools(self) -> list[dict]:
        # TODO: replace with mcp_session.list_tools() against a real server
        return [
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

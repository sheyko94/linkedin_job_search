# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See [README.md](README.md) for a full description of the project, architecture diagram, and configuration reference.

## Infrastructure

OpenSearch runs locally via Docker Compose (`docker-compose.yml` at project root).

```bash
docker compose up -d   # start
docker compose down    # stop and remove containers
```

| Service | URL |
| --- | --- |
| OpenSearch API | `http://localhost:9200` |

## Commands

```bash
uv sync                                          # install / update dependencies
uv run python seed_opensearch.py                 # seed OpenSearch with the mock corpus (run once)
curl "http://localhost:9200/docs/_count?pretty"  # verify data was indexed
uv run python main.py "your query"               # run the system
uv run pytest                                    # run tests
uv run ruff check .                              # lint
uv run ruff format .                             # format
```

## Agent rules

Each agent has a strict scope it must never cross:

- **Orchestrator** (`agents/coordinator.py`) — calls tools only. Never retrieves or synthesises directly.
- **Research Agent** (`agents/research.py`) — searches only. Never answers or draws conclusions.
- **Answer Agent** (`agents/answer.py`) — synthesises only. Never retrieves or invents beyond the provided chunks.

## Key files

| File | Purpose |
| --- | --- |
| `agents/coordinator.py` | Orchestrator Agent — LLM with `run_research` + `generate_answer` tools |
| `agents/research.py` | Research Agent — LLM with `search` tool |
| `agents/answer.py` | Answer Agent — single LLM call, JSON output |
| `agents/models.py` | `AnswerResult`, `QueryResult` |
| `mcp/client.py` | Tool registry — `list_orchestrator_tools`, `list_research_tools` |
| `llm/client.py` | Anthropic API wrapper — `complete`, `complete_with_tools` |
| `opensearch/client.py` | BM25 search client with configurable timeout |
| `opensearch/reranker.py` | Cross-encoder reranking via sentence-transformers |
| `config/settings.py` | All configuration |

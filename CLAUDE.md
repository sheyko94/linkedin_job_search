# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Infrastructure

OpenSearch runs locally via Docker Compose (`docker-compose.yml` at project root).

Start:

```bash
docker compose up -d
```

Stop and remove containers:

```bash
docker compose down
```

| Service | URL |
| --- | --- |
| OpenSearch API | `http://localhost:9200` |

The retrieval layer (`retrieval/search_client.py`) connects to OpenSearch at `:9200` and runs a BM25 `match` query against the `docs` index.

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

## Architecture

See [docs/architecture.md](docs/architecture.md) for a sequence diagram of the full flow.

Two-agent pipeline orchestrated by the coordinator:

```text
main.py → app/coordinator.py → agents/retriever.py (Research Agent) → retrieval/search_client.py → OpenSearch
                              → agents/executor.py  (Answer Agent)   → llm/client.py
```

**Contracts** (`app/models.py`) are the backbone — every agent boundary uses a strict Pydantic model. `UserTask` in, `OrchestratedResult` out. Never pass free text between agents.

**Research Agent** (`agents/retriever.py`) uses Claude's tool-use API with a `search` tool. Claude decides how many times to search and with what queries. Returns `RetrievalResult` — it must never answer or draw conclusions.

**Answer Agent** (`agents/executor.py`) receives the query + retrieved chunks and calls Claude to produce a grounded `ExecutionResult` (answer, citations, confidence, missing_information). It must never retrieve data or invent information not in the chunks.

**LLM layer** (`llm/`): `client.py` exposes `complete` (single call) and `run_agent` (tool-use loop). `prompts.py` owns all system prompts. `parser.py` extracts JSON from the LLM response.

**Retrieval** (`retrieval/search_client.py`): connects to OpenSearch and runs a BM25 `match` query.

**Observability** (`observability/logging.py`): structlog configured for JSON output to stderr. Call `configure()` once at startup (done in `main.py`). All modules use `get_logger(__name__)`.

## Configuration

Via `.env` (copy from `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | required | |
| `MODEL` | `claude-sonnet-4-6` | |
| `RETRIEVAL_TOP_K` | `5` | |
| `OPENSEARCH_URL` | `http://localhost:9200` | |
| `OPENSEARCH_INDEX` | `docs` | |

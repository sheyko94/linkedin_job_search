# Agents System

A multi-agent RAG (Retrieval-Augmented Generation) pipeline built with the Anthropic Claude API. Three specialised LLM agents collaborate to answer queries grounded exclusively in a knowledge base — no hallucination, citations included.

## How it works

A user query flows through three agents:

1. **Orchestrator** — an LLM agent that decides when to search, when to answer, and whether to iterate. It never retrieves or synthesises directly.
2. **Research Agent** — an LLM agent that drives OpenSearch queries via tool use until it has gathered enough evidence.
3. **Answer Agent** — an LLM that synthesises the collected evidence into a grounded answer with citations and a confidence score.

If the answer is incomplete or confidence is low, the orchestrator sends the identified gaps back to the research agent and tries again — up to `MAX_ATTEMPTS` times.

```mermaid
sequenceDiagram
    actor User
    participant Orchestrator as Orchestrator Agent
    participant Research as Research Agent
    participant OpenSearch
    participant Reranker
    participant Answer as Answer Agent

    User->>Orchestrator: query

    loop Orchestrator tool-use loop (Claude decides when to stop)
        Orchestrator->>Research: tool_use: run_research(gaps?)

        loop Research tool-use loop (Claude decides)
            Research->>OpenSearch: BM25 search(query)
            OpenSearch-->>Research: chunks
        end

        Research-->>Orchestrator: accumulated chunks

        Orchestrator->>Answer: tool_use: generate_answer()
        Orchestrator->>Reranker: rerank(chunks) [if enabled]
        Reranker-->>Orchestrator: top-K chunks
        Answer->>Answer: LLM call — query + top-K chunks
        Answer-->>Orchestrator: confidence, missing_information
    end

    Orchestrator-->>User: QueryResult
```

```mermaid
flowchart LR
    User([User]) -->|query| Orch

    Orch["Orchestrator Agent<br/>(LLM tool-use loop)"]
    Orch -->|"run_research(gaps?)"| ResAgent

    subgraph ResAgent["Research Agent"]
        Res["LLM tool-use loop"] -->|search query| OS[(OpenSearch<br/>BM25)]
        OS -->|chunks| Res
    end

    ResAgent -->|accumulated chunks| Reranker["Reranker<br/>(cross-encoder, optional)"]
    Reranker -->|top-K chunks| AnsAgent

    subgraph AnsAgent["Answer Agent"]
        Ans["Single LLM call"]
    end

    AnsAgent -->|AnswerResult| Dec{"Confident<br/>and complete?"}
    Dec -->|yes| Result([QueryResult])
    Result --> User
    Dec -->|"no — attempts left"| Orch
    Dec -->|"max attempts reached"| Result
```

## Project structure

```
agents/
  coordinator.py   — Orchestrator Agent (LLM with run_research + generate_answer tools)
  research.py      — Research Agent (LLM with search tool)
  answer.py        — Answer Agent (single LLM call, JSON output)
  models.py        — Shared Pydantic models (AnswerResult, QueryResult)

llm/
  client.py        — Anthropic API wrapper (complete, complete_with_tools); token accounting + latency logging

mcp/
  client.py        — Tool registry (list_orchestrator_tools, list_research_tools)

opensearch/
  client.py        — BM25 search client with configurable timeout
  models.py        — RetrievedChunk, RetrievalResult
  reranker.py      — Cross-encoder reranking via sentence-transformers

config/
  settings.py      — Typed config via pydantic-settings
  logging.py       — structlog JSON output with distributed trace ID support
  display.py       — Rich terminal rendering

main.py            — CLI entry point (input validation)
seed_opensearch.py — Seeds OpenSearch with the mock corpus
```

## Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker

**1. Install dependencies**

```bash
uv sync
```

**2. Configure environment**

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY
```

**3. Start OpenSearch**

```bash
docker compose up -d
```

**4. Seed the knowledge base**

```bash
uv run python seed_opensearch.py
```

Verify data was indexed:

```bash
curl "http://localhost:9200/docs/_count?pretty"
```

## Usage

```bash
uv run python main.py "your query here"
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | required | Anthropic API key |
| `ORCHESTRATOR_MODEL` | `claude-sonnet-4-6` | Model for the orchestrator agent |
| `RESEARCH_MODEL` | `claude-haiku-4-5-20251001` | Model for the research agent |
| `ANSWER_MODEL` | `claude-haiku-4-5-20251001` | Model for the answer agent |
| `RETRIEVAL_TOP_K` | `5` | Number of chunks returned per BM25 search |
| `OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch endpoint |
| `OPENSEARCH_INDEX` | `docs` | Index name |
| `OPENSEARCH_TIMEOUT` | `2.0` | Per-request timeout in seconds for OpenSearch queries |
| `MAX_ATTEMPTS` | `3` | Max answer attempts before the orchestrator stops |
| `MAX_SEARCH_ITERATIONS` | `10` | Max tool-use iterations for the research agent |
| `ORCHESTRATOR_TIMEOUT` | `60.0` | Wall-clock timeout in seconds for the full orchestrator run |
| `RERANKER_ENABLED` | `true` | Enable cross-encoder reranking before answer generation |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Sentence-transformers cross-encoder model |
| `RERANKER_TOP_K` | `3` | Number of top chunks passed to the answer agent after reranking |
| `MAX_QUERY_LENGTH` | `2000` | Maximum allowed query length in characters |

## Development

```bash
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
docker compose down    # stop OpenSearch
```

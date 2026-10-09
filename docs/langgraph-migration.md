# LangGraph and LangChain walkthrough

The coordinator and search loop are LangGraph graphs. All model calls use LangChain
through the shared initializer. Domain validation, browser automation, and report
formatting remain application code.

## Framework responsibilities

| Concern | Framework handles | Application handles |
| --- | --- | --- |
| Pipeline execution | Nodes, edges, routing, streamed state updates | Stage implementations and stop conditions |
| Model requests | Provider adapters, prompt composition, request concurrency | Input authority, budgets, prompts |
| Structured responses | Pydantic tool schemas and parsing | Job-ID coverage and semantic checks |
| Tool execution | ToolNode dispatch, validation feedback, ToolRuntime injection | Browser operations and sequential state merging |
| Runtime dependencies | Typed graph context | Browser lifetime and sync thread ownership |
| Observability | Usage aggregation and custom progress transport | Local trace format and Rich rendering |
| Diagrams | Compiled graph Mermaid export | Explanatory diagrams and documentation |

No checkpointer, interrupted-run resume, or graph retries are enabled.

## 1. Read the coordinator

Start with [PipelineState and build_graph](../agents/coordinator.py).

`PipelineState` contains the full profile, full criteria, typed search guidance,
collected jobs, matches, skill gaps, and typed `SearchSnapshot` history. Nodes return partial
updates. Lists use replacement; accumulating stages return new complete lists.

The normal flow is:

```text
load_inputs → search → deduplicate → match → analyze_gaps → persist
                                       ↓
                                     refine → search (if another pass is allowed)
```

Conditional edges enforce pass count, a soft monotonic deadline, and no-new-job
termination. `MAX_REFINEMENT_ITERATIONS` counts search passes; one means no refinement.
In-flight search still finishes and its new jobs are matched. See the
[application workflow](application-flow.md) for all branches.

`_to_session` adapts workflow state to the report/display contract. Graph state and
the output model have different lifetimes, so this adapter remains intentional.

## 2. Read a structured model component

Read [skills_gap.run](../agents/skills_gap.py), then [matcher.run](../agents/matcher.py)
and [refinement.run](../agents/refinement.py).

Each module owns its prompt and response contract. Discard hints are loaded once
by the coordinator and passed explicitly to search and matcher. The common pattern is:

```python
model = create_chat_model(...)
chain = prompt | model.with_structured_output(
    ResponseSchema, method="function_calling", include_raw=True
)
response = chain.invoke(inputs)
parsed = parse_structured_response(response, ResponseSchema)
```

LangChain derives schemas and parses responses. The shared parser propagates errors
and checks the expected model type. It does not replace component-specific checks.

Matcher validates unique input IDs, splits jobs by `MATCHER_BATCH_SIZE`, and uses
`batch_as_completed` with bounded concurrency. It emits completion counts, restores
input order, then checks that each batch has exactly one result per supplied ID.
Unknown, duplicate, or missing result IDs are errors. Refinement returns a validated
`SearchGuidance`; skills analysis converts structured gaps to domain objects.

All four model components receive full profile and criteria. The matcher does not
receive generated search advice. See [prompt policy](prompt-policy.md).

## 3. Read the search graph

Read [SearchState and build_search_graph](../agents/search.py), then
[tools/search_tools.py](../tools/search_tools.py).

The inner graph has three nodes: `model`, `tools`, and `enrich`. Message updates use
`add_messages`; jobs and counters use replacement. The model binds static tools and
requests listing searches or details. Routing returns to the model until it finishes
or reaches budgets, then goes to final enrichment.

The model client is created on first node execution so graph topology can be exported
without credentials. The listing-call budget is
`ceil(MAX_TOTAL_JOBS / MAX_JOBS_PER_SEARCH)` and the model-call limit is 15.
The listing tools enforce budget limits before navigation.

`ToolNode` handles dispatch, argument validation, and runtime injection. A small
sequential adapter processes one call at a time so subsequent calls see earlier
`Command` updates. This protects job accumulation and budgets when a model requests
multiple tools. Validation and unknown-tool replies provide feedback; unrelated
execution failures propagate.

`SearchContext` supplies the browser and prior-pass IDs outside graph state.
[BrowserSession](../tools/browser_session.py) owns sync Playwright on one worker
thread. It copies execution context so logs and progress events reach the same run.

Both explicit details and final enrichment call
[fetch_job_details](../tools/job_details.py). That operation delays, fetches, merges
nonblank fields, and derives engagement evidence. Navigation failure or an empty
description produces `JobDetailError`: the tool provides model feedback; enrichment
counts it and continues. Unexpected programming failures still propagate.

## 4. Follow refinement and storage

The coordinator passes typed guidance directly to search and stores it through
[storage/writer.py](../storage/writer.py). `.state/search_guidance.json` is canonical;
`.state/search_params.md` is a generated view. With no JSON, search uses base criteria.
Malformed JSON is an error. There is no custom Markdown parser or legacy text path.

Reports record per-pass guidance and filters, plus actual refinement objects.
[presentation/reports.py](../presentation/reports.py) renders Markdown without file
I/O. Storage writes it exclusively into the timestamped run folder. Previous run
outputs remain untouched. See [structured refinement](refinement-and-search-guidance.md).

## 5. Follow progress and usage

`coordinator.run` streams custom events and root values in the v2 format, including
nested graph events. Stage/count events reach Rich callbacks; profiles and descriptions
are not UI progress payloads. Root values become final pipeline state.

One `UsageMetadataCallbackHandler` at the root aggregates provider-reported usage,
including matcher workers. The coordinator saves `token_usage.json` even on failure.
The per-model logging callback still observes latency, errors, and raw responses.
See [framework components](framework-components.md) for the four framework additions.

## 6. Find code by responsibility

See [project structure](project-structure.md) for folders and the ordered simplification.
Regenerate the [coordinator](generated/coordinator.md) and [search](generated/search.md)
diagrams after changing topology:

```bash
uv run python -m scripts.export_graphs
```

Verification uses lint, formatting, import checks, and offline execution. Tests are
added only when explicitly requested. No live model/browser call is necessary for
these checks.

References: [graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[structured output](https://docs.langchain.com/oss/python/langchain/models#structured-output),
[tools](https://docs.langchain.com/oss/python/langchain/tools),
[Playwright threading](https://playwright.dev/python/docs/library#threading).

[Back to documentation](README.md).

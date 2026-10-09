# Framework components: the next four changes

These changes keep the coordinator's workflow and input authority while using more
LangChain and LangGraph facilities. No checkpointer or run-resume mechanism is involved.

## 1. Token accounting

Previously, the search graph manually added token counts to its state after each
model call. That only covered search. Now `coordinator.run` creates one
`UsageMetadataCallbackHandler` and attaches it to the root graph configuration:

```python
usage = UsageMetadataCallbackHandler()
config = {"callbacks": [usage], "recursion_limit": ...}
```

LangChain propagates callbacks through nested graph and model execution, including
matcher worker threads. The handler aggregates provider-reported usage by model,
with cache details when present. Stages using the same model share one aggregate.
The search state's manual `input_tokens` and `output_tokens` fields are removed.

The coordinator exposes usage on `SearchSession.token_usage`, the CLI shows total
input/output counts, and `storage.writer.save_token_usage` saves `token_usage.json`
in the timestamped run folder. The file includes completion status, totals, and
per-model details. A `finally` block also saves partial usage after a failed run.
An empty usage map means no usage was reported; it does not establish zero billing.
This is token accounting, not a monetary estimate or a record of all failed API attempts.

`ModelLoggingCallback` remains responsible for per-call timing, errors, and local
raw response traces. It observes individual usage but no longer needs to accumulate it.

## 2. Model construction

Previously, `create_chat_model` directly constructed `ChatAnthropic`. It now returns
the standard `BaseChatModel` interface using LangChain's initializer:

```python
init_chat_model(
    model=name,
    model_provider=provider,
    max_tokens=max_tokens,
    callbacks=[ModelLoggingCallback(...)],
    **credentials,
)
```

Bare names such as `claude-haiku-4-5-20251001` retain Anthropic as the provider.
An explicit `anthropic:claude-haiku-4-5-20251001` name works too. Other provider
prefixes select their installed LangChain integration; no component needs a
provider-specific import. Anthropic's key comes from application settings and is
required when constructing that provider's client. Other integrations use their
own shell environment credentials. The project only installs the Anthropic integration
by default; this change does not install or validate other providers.

Each selected model must support the stage's existing tool-calling and structured
output options. LangChain's common interface does not guarantee identical provider
capabilities. Response validation and job coverage checks remain in the components.

## 3. Graph diagrams from code

Run from the repository root:

```bash
uv run python -m scripts.export_graphs
```

The exporter calls both graph builders, then `get_graph().draw_mermaid()`, writing
[the coordinator](generated/coordinator.md) and [search graph](generated/search.md).
It performs no model calls or browser navigation and needs no API key. Search model
construction happens on the first model-node execution, so topology is available
without creating a client. Building the graph does not run it.

Regenerate after changing nodes or edges. The exporter replaces only these two
generated documents. The explanatory application, search, and data-flow diagrams
remain useful for intent and resource ownership; they are maintained separately.

## 4. Detailed progress streaming

Previously, the UI consumed node-start events only. Now the coordinator streams
`custom` and `values` in the uniform v2 event format, with nested graph events enabled.
`get_stream_writer()` in nodes and `runtime.stream_writer` in tools emit explicit events:

```python
get_stream_writer()({"kind": "matching", "completed": completed, "total": len(batches)})
```

- Coordinator nodes announce stage starts.
- Listing tools report the collected-job count for the current search pass.
- Explicit detail tools report whether a description was obtained.
- Final enrichment reports attempted fetches and fetch errors. It runs on the
  browser worker; the existing context propagation preserves the stream writer.
- Matcher uses `batch_as_completed()` to announce completed requests immediately,
  including when concurrency is greater than one. It restores input order before
  validating and combining responses. Completion is not a claim that a response
  passed validation; validation failures still stop the run.

The root consumer only accepts root-graph `values` as pipeline state, so nested search
state cannot overwrite it. Custom events go through `on_stage` or `on_progress` to
`presentation.cli` and the Rich CLI. Progress contains counts and status, not profile
contents, model responses, or job descriptions. It is ephemeral and is not saved
as resumable progress.

Sources: [LangChain models and usage](https://docs.langchain.com/oss/python/langchain/models),
[LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming),
[graph visualization](https://docs.langchain.com/oss/python/langgraph/use-graph-api).

[Back to documentation](README.md).

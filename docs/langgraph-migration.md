# LangGraph migration and framework walkthrough

Steps 1–3 are implemented: LangGraph runs the outer workflow and the search subgraph.
All model calls use LangChain `ChatAnthropic`; matching and skills-gap analysis use structured
responses. Existing LinkedIn scraping functions remain the browser-tool implementations.
The CLI still calls `agents.coordinator.run()` and receives a `SearchSession`.
The coordinator creates a timestamped output folder and trace before graph execution;
that folder is carried in graph state and the returned session.

### Improvements after the architecture review

The graphs retain their existing nodes and edges. These changes improve the behavior inside
those nodes and the information in the report:

1. **Login failure is an error.** `search.run` raises `LinkedInAuthenticationError` when
   authentication fails. The CLI provides login guidance; result reports are not overwritten
   with an empty successful search.
2. **Enrichment preserves collected details.** `_enrich_jobs` fetches only jobs without a
   nonblank description, subject to the existing title filter. `apply_job_details` merges
   nonblank string fields, so incomplete detail responses do not erase known data.
3. **Invalid tool arguments produce feedback.** The tools node validates arguments before
   execution and returns an error `ToolMessage` for model-facing field errors. The model can
   correct its next call within the same bounded loop. Runtime failures still propagate.
4. **Refinement learns from rejected jobs.** Bounded examples from all match categories
   carry reasons. The prompt distinguishes adjustable advice from fixed URL filters.
5. **Formatting is shared.** `config/job_formatting.py` renders the same context for matcher
   input and report output. It takes an explicit description limit and has no model dependency.
6. **Settings reject invalid numeric limits.** Positive sizes and finite timeout values
   prevent invalid batch ranges and budget calculations.
7. **Reports explain each search's inputs.** `_search_jobs` appends input snapshots to
   `search_params_used`; `_to_session` passes them to the writer. Each iteration's collapsible
   section shows guidance, base criteria, and effective filters. These are inputs, not exact
   executed queries; actual tool calls appear in the execution trace. Snapshots exclude
   credentials and the profile and provide no checkpointing or resume behavior.
8. **Model setup and logging are shared.** `agents/model_client.py` provides a small factory
   and a LangChain response callback. Each component retains its prompt, schema, invocation, and parsing;
   search retains its aggregate graph metrics.

### Implemented graphs

The [outer workflow diagram](application-flow.md) shows the coordinator's nodes
and conditional routes. Its `search` node calls `search.run()`, which opens browser
resources and invokes the [search graph](search-flow.md). The diamonds in these
diagrams explain conditional-edge functions; they are not separate graph nodes or
LLM calls.

### What the framework owns

| Responsibility | Framework mechanism | Application logic retained |
| --- | --- | --- |
| Stage execution and looping | LangGraph nodes and conditional edges | Stop rules, iteration count, deadline policy |
| Shared workflow data | Graph state updates and Command | Job-ID deduplication and accumulation rules |
| Runtime dependencies | Runtime context and ToolRuntime injection | Browser lifecycle and ownership |
| Model/tool loop (step 3) | Explicit subgraph and ToolNode | Browser tools, prompts, budgets, sequential state handoff |
| Model calls and response parsing (step 2) | LangChain `ChatAnthropic` and structured output | Schemas, scoring rules, completeness validation |
| Model response logging | LangChain callbacks | Local trace format and metrics |
| Terminal progress | LangGraph task stream + Rich | Stage labels and presentation |
| Scraping and reporting | Existing Python functions | Login, cookies, selectors, pagination, Markdown formatting |

LangGraph executes the workflow; LangChain model/tool helpers are a separate adoption step.
LangGraph does not infer search strategy, scoring rules, or timeout policy from the graph.

### Incremental plan

1. **Outer orchestration — implemented.** Wrap existing functions in nodes, replace the
   coordinator's loop with edges, preserve reports and the CLI return type. Import and inspect the graph before a live run.
2. **Simple model calls — implemented.** Skills-gap analysis (step 2a), matching (step 2b),
   and refinement (step 2c) use `ChatAnthropic`. Matching validates batch coverage and score
   bounds; refinement returns validated SearchGuidance from its own module.
3. **Search tool loop — implemented.** A subgraph executes model, tools, and enrichment
   nodes. Messages and tool results are local search state. Browser operations run
   sequentially on one dedicated thread; browser handles stay outside graph state.
4. **Recovery — skipped by request.** No checkpointing or resume support is planned.
5. **Cleanup and terminal progress — implemented.** Remove the unused SDK wrapper and
   direct Anthropic dependency, then stream graph task-start events into Rich stage updates.

### Step 1 walkthrough: read the code in this order

All workflow code is in `agents/coordinator.py`:

1. **`PipelineState`: the data.** A `TypedDict` describes inputs, current parameters,
   iteration count, deadline, current jobs, accumulated jobs/matches, and final gaps.
   `iteration` starts at zero and counts searches started. Lists retain the existing
   domain models; an ID-keyed representation can be introduced later if necessary.
2. **Node functions: the work.** Each function accepts state and returns a dictionary
   containing only the fields it updates. `_search_jobs` calls the existing search agent;
   `_match_jobs` calls the existing matcher. These are wrappers, not new agents.
3. **State updates: replacement.** No custom reducers are used. Returning
   `{"matched_jobs": state["matched_jobs"] + new_matches}` replaces that field with the
   complete accumulated list. Returning only `new_matches` would lose prior iterations.
   The code builds new lists rather than mutating the input state.
4. **Routing functions: the decisions.** `_can_search` checks iterations and the deadline.
   Conditional-edge functions return the next node's name. Empty or already-seen search
   results go directly to final gap analysis.
5. **`build_graph`: the wiring.** `add_node` registers the work, `add_edge` declares a
   fixed transition, and `add_conditional_edges` declares a branch. `compile()` builds
   the executable graph. Nothing calls an LLM merely to decide which stage runs next.
6. **`run`: the adapter.** Initialize state, stream the graph, then use `_to_session`
   to return the existing `SearchSession`. Reports and terminal display keep their
   existing interfaces. Logging context is cleared even if a node raises an exception.

Example with two iterations: search returns jobs A and B; matching scores both. Refinement
updates the parameters. The next search returns B and C; deduplication leaves only C for
matching. Gap analysis receives the matches for A, B, and C, and reports are written once.

Preserved behavior and current limits:

- `MAX_TOTAL_JOBS` remains a cap **per search iteration**.
- There is no refinement after the final iteration and no refinement when no new jobs
  are found. Existing saved parameters are reused; missing parameters bootstrap from criteria.
- The deadline stops new searches/refinements. An in-flight search is still followed by
  matching; final gap analysis and report writing still run after deadline expiry.
  A refinement call can overrun the deadline, so routing checks again before the next search.
- Gap analysis happens after the loop, so the refinement prompt has no computed gaps yet.
- Graph `recursion_limit` counts execution steps, not searches or elapsed seconds. `run`
  sizes it for the configured iteration count; application rules end the loop normally.
- There is no checkpointing, graph retry policy, or concurrent browser operation.
  The SDK wrapper was removed during cleanup. The monotonic deadline is process-local;
  persistent resume remains outside the project scope.

### Step 2a walkthrough: skills-gap model call

Read `agents/skills_gap.py` in this order:

1. **`SkillGapItem` and `SkillsGapResponse`: the response contract.** Python types replace
   the hand-written JSON tool schema. The outer response contains `gaps`; each item has a
   skill, category, frequency, and priority. The old parser's defaults (`Other`, `1`, `Low`)
   are preserved, and `Literal` restricts priority to the same three options as before.
2. **`ChatAnthropic`: the provider adapter.** The agent supplies the existing API key,
   `SKILLS_GAP_MODEL`, and 2,048-token limit. It is constructed only when analysis is needed.
3. **`with_structured_output`: the parsing setup.** LangChain derives a tool schema from
   Pydantic and handles extraction and validation. Explicit `method="function_calling"`
   retains forced tool output. This schema tool returns data; it is not a browser operation.
4. **`invoke`: the request.** System and human messages retain the priority rules and
   matched-job context. Only the final prompt instruction changes from the old named tool
   to the new structured response schema.
5. **Raw output and errors.** `include_raw=True` returns raw metadata, parsed data, and any
   parsing error. Token counts, call latency, and tool output still feed the execution trace.
   The agent raises parsing errors or missing structured responses rather than reporting an
   empty successful analysis. Valid `gaps=[]` is still accepted.
6. **The domain adapter.** Parsed response items are converted to existing `SkillGap`
   objects. The coordinator's graph node and report writer keep their interfaces.

Before: `complete_json` → extract tool input dictionary → `_parse` → `list[SkillGap]`.
After: `ChatAnthropic` → `with_structured_output` → validated response → `list[SkillGap]`.

Pydantic validates structure and types; it does not verify the model's skill counts or
prioritization. Those decisions remain in the prompt. Empty inputs and results with no
missing skills still return immediately without calling the model.

This step adds `langchain-anthropic`; its dependency requirements also upgrade the Anthropic
SDK in the lockfile. Step 3 also migrates the search model calls to LangChain.
Routine migration verification uses import/compilation checks and `uv run ruff check .`;
tests are added only when explicitly requested. No live API call is needed for these checks.

### Step 2b walkthrough: matcher model calls

Read `agents/matcher.py` in this order:

1. **`MatchItem` and `MatchesResponse`: the response contract.** Pydantic replaces the
   hand-written JSON schema. `score` has enforced bounds of 0–1; recommendation is one of
   the four existing labels. Optional skill lists and reason preserve their previous defaults.
   The model returns a `job_id`, not a reconstructed `JobPosting`.
2. **`run`: preprocessing.** Empty input still returns immediately. Duplicate input job IDs
   now fail explicitly because they make a one-result-per-ID contract ambiguous. The existing
   description-based dealbreaker filter still produces deterministic Skip results locally.
3. **Model setup and batching.** When jobs remain to score, create `ChatAnthropic` with the
   existing matcher model, API key, and 4,096-token limit. Reuse its structured-output wrapper
   across the existing sequential batches. If all jobs were auto-skipped, no model is created.
4. **Invocation and trace.** `invoke` receives the existing profile and formatted job
   descriptions. `method="function_calling"` retains forced tool output. `include_raw=True`
   keeps token counts, latency, and raw tool output for the trace. Parsing errors propagate.
5. **`_to_match_results`: validation and the domain adapter.** Compare returned IDs with the
   supplied batch and reject missing, unknown, or repeated IDs before accepting any results
   from that batch. Then attach each original `JobPosting` and construct the existing
   `MatchResult`. The coordinator and writers keep their interfaces.

For a batch containing jobs A and B, the response must contain A and B exactly once each.
A response containing only A, two copies of A, or an extra job C raises a descriptive error.
Previously missing results could pass unnoticed, duplicates could accumulate, and unknown
IDs were silently ignored. Scores outside 0–1 now fail Pydantic validation. These are
intentional stricter checks, not new scoring rules or automatic retry loops.

The hard-blocker prompt and scoring context are preserved; the final instruction now asks
for the structured response and explicitly includes skipped jobs. Schema and coverage checks
do not verify that the model correctly applied every blocker or assigned a good score.
The outer LangGraph topology remains the same: its `match` node calls this migrated function.

### Step 2c walkthrough: structured refinement

Read the [structured refinement walkthrough](refinement-and-search-guidance.md), then
`SearchGuidance` in `agents/models.py`, `agents/refinement.py`, and `_refine_params`
in `agents/coordinator.py`.

Refinement uses `with_structured_output` with `SearchGuidance`,
`method="function_calling"`, and `include_raw=True`, just like matching and gap
analysis. New search regions are allowed; repeated priorities are removed.
The coordinator passes the
validated object directly to search and renders a readable Markdown file with the
same JSON payload. Legacy Markdown remains supported for initial guidance.

Matcher, gap analysis, and refinement are model-powered workflow steps. Search is
the agent that chooses and executes tools. A graph node need not contain an autonomous
agent. All model calls use LangChain; the Anthropic SDK is a transitive dependency.

### Step 3 walkthrough: search agent subgraph

Read `SearchState`, `build_search_graph`, and `run` in `agents/search.py`, then
`tools/browser_session.py`:

1. **Local state.** `SearchState` holds messages, collected jobs by ID, listing-call and
   model-call counters, token totals, and a stop reason. It is separate from the outer
   pipeline state. `search.run` returns `list[JobPosting]` to the coordinator as before.
2. **Messages reducer.** `messages` uses `add_messages`: nodes return only new messages,
   and LangGraph merges them into the conversation. Job dictionaries and counters use
   replacement updates. Tool nodes copy job objects before changing them.
3. **Model node.** `ChatAnthropic.bind_tools` makes the two typed LangChain tools available
   to Claude. The model node applies the prompt template to message history and returns an `AIMessage` plus
   usage updates. Its response can contain text, tool requests, or both.
4. **Tools node.** Execute requested calls sequentially using the existing scraper functions.
   LangChain creates each `ToolMessage` with the matching `tool_call_id`. Results update
   `jobs_by_id` through Command updates; model-generated summaries never create job records.
   A sequential adapter invokes ToolNode with the static tools in `tools/search_tools.py`.
5. **Conditional routing.** With tool requests, go from model to tools; with no requests,
   go to enrichment. After tools, repeat the model call only if the listing budget, job cap,
   and 15-model-call limit permit it. Allow the final model response's tools to execute before
   stopping at the model-call limit. This replaces the SDK's manual conversation loop.
6. **Browser ownership.** Sync Playwright is not thread-safe, and graph nodes may execute
   on different worker threads. `BrowserSession` owns a single dedicated worker: browser
   setup, login, navigation, enrichment, and cleanup execute there. `call(function, ...)`
   waits for `function(page, ...)` to complete. Logging context is copied into the worker.
   Live browser objects are supplied through typed runtime context, outside graph state.
7. **Enrichment and cleanup.** Title-based discard filtering, detail delays, per-job error
   handling remain explicit. Both the detail tool and enrichment share an eligibility rule
   that also skips previously processed IDs. Enrichment preserves
   known fields when a fetch returns incomplete data. The context manager
   closes browser resources even when the graph fails. Checkpointing remains excluded.

```text
HumanMessage → model → AIMessage(tool_calls)
                     → tools → ToolMessage(s) → model ...
                     → enrichment → actual collected jobs
```

The scrape-call budget remains `ceil(MAX_TOTAL_JOBS / MAX_JOBS_PER_SEARCH)` per outer
iteration; the model-call limit remains 15. Both tools remain available. Listing searches
check budgets before execution, including when a response asks for several tools. Once a
budget is reached, routing goes directly to enrichment rather than requiring an extra model
request to trigger the old `_LimitReached` exception. Unknown tool names return an explicit
message; browser or API failures otherwise propagate as before.

The search graph records token totals and termination reason in `llm_search_graph`;
its total latency includes login, graph execution, enrichment, and cleanup. Tool arguments,
results, and model text still appear in the trace. Construction/import/lint checks do not
exercise a live model, LinkedIn scraping, or login.

Threading reference: [Playwright library guidance](https://playwright.dev/python/docs/library#threading).

### Cleanup and terminal progress walkthrough

1. **Dependencies.** `llm/anthropic.py` had no remaining callers and is removed. The project
   no longer declares `anthropic` directly; `langchain-anthropic` supplies the SDK transitively.
2. **Execution stream.** `coordinator.run` uses `graph.stream` with `tasks` and `values` modes.
   Task-start events identify nodes as they begin; values events supply the latest graph
   state. Consume the stream to completion, then return the same `SearchSession` as before.
3. **UI boundary.** `run(on_stage=...)` accepts an optional callback receiving only a node
   name. Graph state, profiles, and descriptions are not forwarded to the display callback.
   Callers can still use `run()` without providing a callback.
4. **Rich presentation.** `main.py` translates node names through `config.display.stage_label`,
   updates the active spinner, and prints a stage line. Repeated iterations print repeated
   stages, and branches that do not run produce no stage line. Existing JSON logs and final
   results remain available. A stage line marks a start, not successful completion.

Typical one-iteration stage sequence:

```text
Loading profile and search criteria…
Searching LinkedIn and fetching job descriptions…
Removing jobs already found…
Matching jobs against your profile…
Analyzing missing skills…
Saving reports…
```

Progress covers outer pipeline stages. The search subgraph's model calls and browser details
remain in the execution trace. Streaming does not save progress: checkpointing and resume
support are deliberately excluded. This change adds no new runtime dependencies.

### Prompt templates

Each component defines `_PROMPT` with LangChain `ChatPromptTemplate` beside its existing
system instructions. The instruction wording remains a multiline string; the prompt object
represents message roles, named inputs, and composition with the model.

| Component | Template inputs | Model output |
| --- | --- | --- |
| Matcher | `profile`, `jobs` | Parsed `MatchesResponse` and raw metadata |
| Skills gap | `results` | Parsed `SkillsGapResponse` and raw metadata |
| Refinement | `session_context` | Parsed `SearchGuidance` and raw metadata |
| Search | `messages` via `MessagesPlaceholder` | AI message containing text/tool calls |

```python
_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", "## User Profile\n{profile}\n\n## Job Postings\n{jobs}"),
])
chain = _PROMPT | structured_model
response = chain.invoke({"profile": profile_md, "jobs": _format_jobs(batch)})
```

The pipe composes formatting followed by model invocation. Variable values are inserted
as data, so braces within profiles or job descriptions are not interpreted as additional
placeholders. Existing formatting functions still assemble detailed job/session context.
For search, `MessagesPlaceholder` inserts the actual typed conversation, preserving tool-call
IDs and message roles. Search state starts with the human request; the template supplies the
system message once per model request. Graph topology, response validation, budgets, and
trace logging stay the same. Templates remain local to their components; no new dependency
is needed because `langchain-core` is already supplied by the existing integrations.

### Runtime context, ToolNode, and sequential tool execution

Read `tools/search_context.py`, then `build_search_graph` in `agents/search.py`, then
`tools/search_tools.py`.

1. **Runtime context holds dependencies.** `SearchContext` is a frozen dataclass containing
   the browser reference, discard keywords, and IDs processed in prior search passes. `StateGraph(SearchState, context_schema=SearchContext)` declares
   it; `invoke(..., context=SearchContext(browser=browser))` supplies it for the current run.
   Graph construction no longer captures a browser. Nodes use `runtime.context.browser`.
   Collected jobs, messages, and counters remain state. Browser ownership still belongs to
   `BrowserSession`; context adds no persistence or resume support.
2. **Tool definitions remain static.** `SEARCH_TOOLS` is created once at module import.
   `ScrapeJobsInput` and `JobDetailsInput` contain only public arguments. The functions accept
   `runtime: ToolRuntime[SearchContext]`, which `ToolNode` supplies automatically and hides
   from the model. There is no `SearchToolContext`, manual injected-argument assembly, or
   separate tool-name registry.
3. **Tools return state changes.** They read `runtime.state`, copy jobs before updating
   them, and return `Command(update=...)` containing updated jobs/counters and a `ToolMessage`
   whose ID comes from `runtime.tool_call_id`. Listing budget checks live in `scrape_jobs`,
   before browser navigation. A reached budget returns a message without collecting jobs.
4. **The graph adapter preserves ordering.** `execute_tools` invokes `ToolNode` for one
   requested call at a time. It combines each call's state updates into local working data
   before invoking the next call, then returns the final updates to LangGraph. This ensures
   that a later detail call can see jobs collected earlier in the same model response.
   Setting concurrency to one on a whole ToolNode batch would serialize execution but still
   give each call the same initial state snapshot. The adapter retains this application
   requirement while delegating dispatch, injection, validation, and replies to ToolNode.
5. **Errors remain visible.** ToolNode returns error ToolMessages for unknown tools and
   invalid arguments, giving the model feedback within its existing 15-call limit. Its
   default handler propagates other tool failures. Invalid scraped job cards raise an
   execution error rather than being reported as invalid model arguments. Invalid arguments execute no browser
   function and consume no listing budget. Title filters, detail delays, and nonblank-field
   merging remain application logic; the detail tool and enrichment share the eligibility policy.

```python
# Browser supplied at invocation; it is not graph state.
graph = StateGraph(SearchState, context_schema=SearchContext)
compiled.invoke(initial_state, context=SearchContext(browser=browser))

# ToolNode supplies runtime; the model sees only job_url.
def get_job_details(job_url: str, runtime: ToolRuntime[SearchContext]) -> Command | ToolMessage:
    # Fetch and merge details into a copy of runtime.state["jobs_by_id"].
    return Command(update={
        "jobs_by_id": updated_jobs,
        "messages": [ToolMessage(
            content=json.dumps(details),
            tool_call_id=runtime.tool_call_id,
            name="get_job_details",
        )],
    })
```

The sketch omits the existing scraper work; see the source for the complete implementation.
No new dependencies are needed. The outer and search graph topology remain unchanged.

References: [LangGraph runtime context](https://docs.langchain.com/oss/python/langgraph/graph-api#runtime-context),
[LangChain tools and state updates](https://docs.langchain.com/oss/python/langchain/tools).

### Model logging through callbacks

`create_chat_model` attaches a `BaseCallbackHandler` to each ChatAnthropic instance. Matcher,
skills gap, refinement, and search identify their stage when creating the model; structured
stages also provide their response schema's name. Components no longer call a response logger
explicitly after `invoke`.

- `on_chat_model_start` records a monotonic start time for the model's run ID.
- `on_llm_end` records token usage and latency from the AI message and writes the existing
  raw text or tool-output trace. Search also retains its aggregate graph metrics.
- `on_llm_error` releases the run's timing entry and records the error type. It does not
  swallow the model failure or log the exception's potentially sensitive request content.

Each model has its own handler; timing entries are protected for concurrent callbacks and
removed on completion/error. Model-call latency now starts at the framework's model-start
callback, excluding prompt formatting. Logging observes model execution; response parsing
and semantic validation remain in the individual components. A parsing error after a model
response is therefore still raised by that component, rather than treated as a model error.

References: [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api),
[LangChain structured output](https://docs.langchain.com/oss/python/langchain/models#structured-output),
[LangChain agent factory](https://reference.langchain.com/python/langchain/agents/factory/create_agent),
[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).


[Back to documentation](README.md).

# Working in this repository

Read [README.md](README.md) for the application overview and
[DEVELOPMENT.md](DEVELOPMENT.md) for workflows and implementation details. Inspect
actual code before changing behavior; documentation is not proof of a feature.

## Standards and checks

- Use Python 3.12+ and the existing `uv` environment. Ruff uses a 100-character
  line length and the E, F, and I rule sets from `pyproject.toml`.
- Do not add tests unless the user explicitly requests them. Verify changes with
  lint, formatting, imports, and relevant offline execution checks. Preserve meaningful
  validation rather than silently repairing model responses.
- Run `uv run ruff check .`, `uv run ruff format --check .`, and `git diff --check`.
  Use `uv run ruff format .` when formatting changes are needed.
- Run `uv run python -m scripts.export_graphs` when graph topology changes; it refreshes
  generated diagrams in `DEVELOPMENT.md` without browser/model calls or API keys.
- Prompt upload and dataset import write to Langfuse. Evaluation with `--run` calls
  a model. These are distinct from offline checks; do not run them as routine lint.
- Keep documentation in the root README, DEVELOPMENT, and AGENTS files. CLAUDE must
  only reference AGENTS. Do not create a separate guide for every feature.
- Do not read secrets to verify configuration; use `.env.example` and settings defaults.
  Keep `.env`, `.input/`, `.state/`, and `.output/` out of Git. The golden dataset is
  intentionally tracked and includes its frozen input snapshots.
- Do not add graph retries, interrupted-run persistence, checkpointers, or resume
  support. The existing workflows have none. Do not overwrite historical run outputs.

## Ownership

| Folder | Responsibility |
| --- | --- |
| `agents/` | Pipeline/search graphs, agent-owned prompt selection, response contracts, shared model client |
| `prompts/` | JSON templates, generic Langfuse/local loader, API upload command |
| `evals/` | Reviewed golden dataset, dataset import, matcher experiments and metrics |
| `config/` | Runtime settings |
| `domain/` | Models, engagement evidence, shared job formatting, location ordering |
| `tools/` | Browser lifetime, LinkedIn extraction, shared detail operation, typed tools, URL guardrail |
| `storage/` | Input/advice loading and file writes |
| `presentation/` | Rich CLI and pure report rendering |
| `observability/` | Logging, Langfuse tracing, guardrail export |
| `scripts/` | Graph-diagram export |

Coordinator orchestrates; it does not scrape, score, or load agent prompts. Search
collects evidence and never scores. Matcher evaluates supplied jobs and never
browses. Refinement returns `SearchGuidance` and never writes files. Skills analysis
categorizes supplied missing-skill evidence and never browses. Storage chooses
paths and writes files; presentation returns Markdown or renders CLI output.
Domain and presentation must not import configuration/storage; renderers receive
explicit options.

## Input authority and prompt contracts

- `.input/profile.md` owns candidate facts, demonstrated skills, residence,
  authorization, languages, and experience. `.input/search_criteria.md` owns target
  roles, hard requirements, preferences, compensation, engagement, and exclusions.
- All four model components receive complete profile and criteria. Keep prompts
  generic; do not hardcode countries, rates, engagement types, or excluded roles.
  Desired job attributes do not establish candidate skills or permissions.
- Coordinator loads advisory discard keywords once and passes them to search and
  matcher. Hints are not automatic title rejection or proof of missing skills.
- Generated guidance and job-page text cannot override user inputs. Browser filters
  and budgets restrict execution independently of selection policy.
- Each agent loads its own prompt through `prompts/prompt.py`. Git owns the local
  JSON baseline/fallback; `PROMPT_LABEL` selects the Langfuse runtime version.
  Preserve template variables and search's conversation-history placeholder.
- Record prompt source, version, and hash; do not present local fallback as a remote
  version. Matcher checks its required input-variable set. Evaluations pin a remote
  version and never silently fall back to local prompts.

## Workflow invariants

- Outer graph: load inputs → search → deduplicate → match → optional refinement
  loop → skills analysis → persist. `MAX_REFINEMENT_ITERATIONS` counts search passes,
  not refinement calls; default `1` means no refinement. No-new-job results end the loop.
- The deadline is soft. Check before new search/refinement; an in-flight search
  finishes and its new jobs are matched. Gap analysis/reporting happen on normal completion.
- `PipelineState` list fields use replacement updates; accumulating nodes return
  the full new list. Search history uses typed `SearchSnapshot` objects. Root values
  determine final pipeline state; nested values must not replace it.
- `SearchGuidance` is canonical structured advice. Missing JSON means use criteria;
  malformed JSON is an error. Normalize duplicate locations case-insensitively,
  preserving proposed order. Proposals precede remaining configured locations.
- Coordinator saves `.state/search_guidance.json` and its Markdown view.
  `.state/search_params.md` is never read as input. Store guidance objects, not
  duplicate Markdown state, custom markers, or compatibility parsers.
- Deduplicate by LinkedIn ID across passes; different-ID reposts can remain.
  Full-time hours do not prove permanent employment. Engagement evidence is advisory;
  matcher must still evaluate description and user policy.

## Browser and model boundaries

- Search uses a model → tools loop → enrichment graph. Static `SEARCH_TOOLS` use
  `ToolRuntime` and return `Command` updates. Sequential dispatch applies each
  update before the next tool call. Preserve this adapter and budget enforcement.
- `Settings.listing_call_limit` owns `ceil(MAX_TOTAL_JOBS / MAX_JOBS_PER_SEARCH)`.
  Search allows at most 15 model calls; final tool calls still execute before enrichment.
- `SearchContext` contains browser and prior-pass job IDs. Sync Playwright belongs
  to one `BrowserSession` worker thread, including setup/navigation/cleanup. Copied
  context preserves logs and progress. Do not move page operations onto graph threads.
- `tools/job_details.py` owns eligibility, delay, nonblank merge (including location),
  and engagement extraction. Previously processed IDs/nonblank descriptions skip
  fetching. A nonblank partial description currently passes that presence check.
- `JobDetailError` supplies model feedback or enrichment failure counts; unexpected
  programming errors propagate. Runtime URLs go through the minimal hostname
  guardrail; static feed/login URLs do not.
- `create_chat_model` uses `init_chat_model`. Bare names default to Anthropic;
  other providers need their integration and shell credentials. Anthropic credentials
  are checked at client construction. Do not assume provider capabilities are identical.
- Matcher uses native `json_schema`; refinement and skills analysis use
  `function_calling`. Keep shared `parse_structured_response` and agent-specific
  schema checks. Matcher requires unique input IDs and exactly one result per ID.
- Matcher uses `batch_as_completed`, default concurrency `1`, and restores batch
  order. Results within each batch retain model response order. Progress counts
  completed requests, not successful response validation.

## Observability and evaluations

- Restore previous trace/log contexts at exit instead of clearing caller state.
  Keep browser-worker context propagation and session IDs.
- Root `UsageMetadataCallbackHandler` aggregates provider-reported usage by model.
  Save it on success/failure; it is token accounting, not monetary estimation.
  Progress events must not contain profile, model-response, or job contents.
- Each invocation creates an exclusive timestamp/session folder. Reports and traces
  use its start time. Save partial usage after errors; flush Langfuse without replacing
  the workflow result or original exception. Guardrail export must not change enforcement.
- Golden labels are reviewed expectations, not model-generated truth. Dataset inputs
  and labels must stay fixed for comparable experiments. Stable seed IDs update items.
- Strong/Good map to Yes; Weak/Skip map to No. Execution failures count as incorrect
  for accuracy but are excluded from precision/recall/F1. Report error rate separately;
  zero denominators score zero. Binary metrics do not validate explanations, arithmetic,
  match scores, or hard-blocker recommendation consistency.

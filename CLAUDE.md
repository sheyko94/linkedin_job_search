# Project development guide

## Application

A LangGraph job-search workflow with LangChain models, typed browser tools, matching,
optional structured refinement, skills analysis, and timestamped reports.

Read README.md and docs/project-structure.md before changing responsibilities.
Do not add tests unless the user explicitly requests them. Use lint, formatting,
import, and offline execution checks. Do not add interrupted-run persistence or resume.
No graph retries are enabled.

## Boundaries

| Folder | Responsibility |
| --- | --- |
| agents | Pipeline/search graphs, component prompts, shared model client |
| config | Runtime settings |
| domain | Models, engagement evidence, shared job context, location ordering |
| tools | Browser lifetime, LinkedIn extraction, detail operation, typed tools |
| storage | Input/advice loading and file writes |
| presentation | Rich terminal UI and pure report rendering |
| observability | Logs and response traces |
| scripts | Graph export |

Coordinator orchestrates; it does not scrape or score. Search collects evidence and
never scores. Matcher scores against profile and criteria, never browses. Refinement
returns SearchGuidance, never writes files. Skills analysis categorizes supplied
missing-skill evidence, never browses. Storage chooses paths and writes files;
presentation returns Markdown strings or renders CLI output.

## Inputs and outputs

| File | Purpose |
| --- | --- |
| .env | Credentials and optional settings overrides |
| .input/profile.md | Candidate facts, skills, experience, residence, authorization, languages |
| .input/search_criteria.md | Target roles, hard requirements, preferences, compensation, exclusions |
| .input/discard_keywords.txt | Optional advisory keyword hints |
| .state/search_guidance.json | Canonical generated advice loaded on future runs |
| .state/search_params.md | Generated Markdown view; never read as application input |
| .state/cookies.json | Saved browser authentication |
| .output/<timestamp>_<session-id>/ | Exclusive run folder: reports, trace, token_usage.json |

All four model components receive complete profile and criteria. Discard hints are
loaded once by the coordinator and passed explicitly to search and matcher. Keep prompts generic;
do not hardcode countries, rates, engagement types, or role exclusions. Profile facts
and criteria policy have separate ownership. Generated advice cannot override either.
Discard hints are not automatic title rejection or proof of missing skills.

Saved guidance must validate as SearchGuidance. Missing JSON means search uses criteria;
malformed JSON is an error. Markdown is a view and has no compatibility parser.
Refinement saves JSON and its view through the coordinator. Search state carries the
object only; there is no duplicate Markdown state or notification hint.

## Important implementation details

- Outer graph: load_inputs → search → deduplicate → match → optional refine loop →
  analyze_gaps → persist. MAX_REFINEMENT_ITERATIONS counts search passes; default 1.
- Deadline is soft and checked before new searches/refinement; an in-flight search
  finishes and gets matched. No-new-job results end the loop.
- Search history is a typed list of SearchSnapshot objects, not a generic nested dict.
- Domain and presentation do not import config/storage; renderers take explicit options.
- Restore previous trace/log contexts at run exit; do not clear the caller context.
- Settings.listing_call_limit owns the listing-budget formula.
- Lists use replacement updates; accumulating nodes return the full new list.
- Search graph: model → tools loop → enrich. Static SEARCH_TOOLS use ToolRuntime
  and return Command updates. Sequential dispatch applies updates before the next tool.
- SearchContext contains browser and previous-pass IDs. Sync Playwright stays on one
  BrowserSession worker thread; copied context preserves logging/progress.
- Shared tools/job_details.py handles eligibility, delay, fetch, merge, engagement
  extraction. JobDetailError provides tool feedback or enrichment failure counts.
  Unexpected programming errors propagate. Already processed IDs/nonblank descriptions skip fetching.
- Deduplicate by LinkedIn ID across passes. Different-ID recruiter reposts can remain.
- Full-time hours do not prove permanent employment. Engagement evidence is advisory;
  matcher also assesses the complete description against user inputs.
- Matcher uses batch_as_completed with default concurrency 1. Restore input order,
  preserve response parsing and exact batch ID coverage. Completion events count
  model requests, not successful validation.
- create_chat_model uses init_chat_model. Bare names default to Anthropic; other
  providers require their integration and shell credentials. Anthropic key validation
  happens when constructing that client.
- parse_structured_response is shared; keep domain checks in each component.
- Root UsageMetadataCallbackHandler aggregates usage by model, saved on success/failure.
  Custom stage/progress and root values stream in v2 format; nested values must not
  replace pipeline state. Progress payloads do not include profile/model/job contents.
- Each run has a fresh output folder. Never overwrite historical outputs. Refinement
  advice is reusable but does not resume an interrupted run.

## Commands and docs

```bash
uv sync
uv run python main.py
uv run ruff check .
uv run ruff format .
uv run python -m scripts.export_graphs
```

Graph export performs no browser/model calls and needs no API key. Keep generated
coordinator/search diagrams and explanatory documentation aligned with changes.
See docs/langgraph-migration.md, docs/framework-components.md,
docs/refinement-and-search-guidance.md, and docs/prompt-policy.md for walkthroughs.
Historical runtime measurements live in docs/runtime-planning.md and are not current
performance guarantees. Defaults and optional environment settings are documented
in docs/configuration.md; do not read secrets to verify them.

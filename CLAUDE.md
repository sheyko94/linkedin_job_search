# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
uv sync                          # install dependencies
uv run playwright install chromium  # install browser (once)
uv run python main.py            # run the full job search pipeline
uv run ruff check .              # lint
uv run ruff format .             # format
```

## Runtime measurements and budgeting

The first measured Agentic AI contract run on 2026-09-10 completed in **179.4 seconds (2m 59s)**
with these inputs/settings:

- profile: 1,126 words; search criteria: 898 words
- `MAX_TOTAL_JOBS=30`, `MAX_JOBS_PER_SEARCH=10`
- three search calls; 20 unique jobs collected; 19 descriptions enriched
- `JOB_DETAIL_DELAY_MS=3000`, `MATCHER_BATCH_SIZE=15`
- two matcher calls (15 + 5 jobs), one search/match iteration; no refinement step

Observed stage times were 7.5 s for startup/login/planning, 47.4 s for listing searches, 93.8 s
for detail enrichment, 28.6 s for matching, and about 2 s for skills-gap analysis/output. Detail
enrichment was the dominant cost at 4.9 s/job, including the configured 3 s delay.

A second, broader run on the same date used `MAX_TOTAL_JOBS=150`,
`MAX_JOBS_PER_SEARCH=20`, and matcher batches of 20. Eight search calls found 80 unique jobs and
enriched 74 descriptions. It completed in **706.6 seconds (11m 47s)**: 7.5 s startup, 142.8 s
listing search, 400.1 s enrichment (5.4 s/job), 140.4 s matching, and 15.9 s final analysis/output.
The pooled end-to-end throughput across both measured runs is about **8.9 seconds per unique
job**. Unique-job yield can remain below `MAX_TOTAL_JOBS` because query results overlap and the
search-agent call budget is finite.

Use the full runtime-planning guide and measurement table in `docs/runtime-planning.md`. A rough one-iteration
estimate is:

```text
8 s startup
+ 10–30 s × scrape call count
+ enriched jobs × (detail delay + ~2 s browser overhead)
+ 7–45 s × matcher batch count
+ 2–20 s final analysis/output
```

Scrape call count is `ceil(MAX_TOTAL_JOBS / MAX_JOBS_PER_SEARCH)`. More refinement iterations
repeat the expensive search/enrichment/matching stages. `ORCHESTRATOR_TIMEOUT` is only checked
between coordinator stages and does not interrupt an in-flight browser or API call, so it is a
soft deadline rather than a strict wall-clock timeout.

### Employment interpretation and deduplication

The baseline run confused full-time commitment with permanent employment in some
contractor postings. `config/employment.py` now extracts explicit role-specific engagement
evidence; shared formatting shows it to the matcher, whose prompt distinguishes hours from
engagement. Ambiguous wording still requires assessment. See `docs/job-evaluation.md`.
Coordinator deduplication uses only LinkedIn job ID, so recruiter reposts with different IDs
can remain as duplicates. Previously processed IDs skip detail fetching within the same run.

## Configuration files

**Required — must be created before running:**

| File | Purpose |
| --- | --- |
| `.env` | API key and optional runtime overrides (copy from `.env.example`) |
| `.input/profile.md` | Your skills, experience, and job preferences |
| `.input/search_criteria.md` | Base search keywords, location, and filters |

**Optional — created manually, safe to omit:**

| File | Purpose |
| --- | --- |
| `.input/discard_keywords.txt` | Comma-separated keywords, used two ways: (1) in the search agent, a **title** match skips a job before fetching details; (2) in the matcher, a **description** match near requirement language ("years"/"required"/"must have"…) auto-skips the job (score 0). If absent, no jobs are filtered by keyword |

**Auto-generated — never create or edit manually:**

| File | Created by |
| --- | --- |
| `.state/search_params.md` | Coordinator each run; evolves from `search_criteria.md` |
| `.state/cookies.json` | Browser login flow; reused on subsequent runs |
| `<run folder>/matched_jobs.md` | Coordinator after each run |
| `<run folder>/skills_gap.md` | Coordinator after each run |
| `<run folder>/execution_trace.log` | `config/logging.py` — full behind-the-scenes trace (URLs, DOM counts, LLM/tool calls, timings); created fresh in each timestamped run folder |

## Agent rules

Do not add tests unless the user explicitly requests them. During this migration, prefer
import, compilation, and lint checks.

Each agent has a strict scope it must never cross:

- **Coordinator** (`agents/coordinator.py`) — runs the pipeline, calls sub-agents. Never scrapes or scores directly.
- **Search Agent** (`agents/search.py`) — scrapes LinkedIn via browser tools. Typed tools and input schemas are defined in `tools/search_tools.py`. Never scores or analyses.
- **Refinement** (`agents/refinement.py`) — returns validated SearchGuidance. Never scrapes, scores, or writes files; the coordinator persists its output.
- **Matcher Agent** (`agents/matcher.py`) — scores jobs against profile. Never scrapes or browses.
- **Skills Gap Agent** (`agents/skills_gap.py`) — categorises missing skills. Never scrapes or browses.

## Key files

| File | Purpose |
| --- | --- |
| `agents/coordinator.py` | LangGraph orchestration, routing, and persistence |
| `agents/refinement.py` | LangChain structured SearchGuidance; no file writes |
| `agents/search.py` | Search Agent — LLM + Playwright browser tools |
| `agents/matcher.py` | Matcher Agent — single LLM call, JSON output |
| `agents/skills_gap.py` | Skills Gap Agent — single LLM call, JSON output |
| `agents/models.py` | `JobPosting`, `MatchResult`, `SkillGap`, `SearchSession` |
| `agents/model_client.py` | Shared ChatAnthropic construction and automatic logging callbacks |
| `tools/search_tools.py` | Static StructuredTool definitions using ToolRuntime and Command updates |
| `tools/search_context.py` | Typed browser dependency supplied at graph invocation |
| `tools/browser_session.py` | Owns sync Playwright on one dedicated runtime thread |
| `tools/linkedin.py` | LinkedIn scraping: login, URL building, job extraction |
| `config/reader.py` | Load `.input/` and `.state/` files into the pipeline |
| `config/writer.py` | Write results to `.state/` and `.output/` |
| `config/job_formatting.py` | Shared matcher/report context with explicit description limit |
| `config/settings.py` | Settings defaults and optional environment overrides |
| `config/logging.py` | structlog JSON configuration |
| `config/display.py` | Rich terminal output |

## LangGraph migration

Step 1 is implemented in `agents/coordinator.py`: `PipelineState`, node wrappers, conditional
edges, and `build_graph()`. See `docs/application-flow.md`, `docs/search-flow.md`, and
`docs/langgraph-migration.md` for diagrams and the learning walkthrough. The CLI return type and existing agent implementations are preserved.
Step 2a is implemented in `agents/skills_gap.py`: `ChatAnthropic` derives structured tool output
from Pydantic response models and converts it to the existing `SkillGap` domain model.
Step 2b is implemented in `agents/matcher.py`: structured Pydantic responses, score bounds,
and exact batch coverage checks (missing/duplicate/unknown IDs). Duplicate input IDs fail
before scoring. Step 2c is implemented in `agents/refinement.py`: the prompt/formatter move
out of the coordinator. Structured output now returns SearchGuidance. The coordinator
passes it directly to search and saves Markdown containing the same JSON payload. Legacy
Markdown remains supported; marked payloads are parsed and validated on subsequent runs. Step 3 is implemented in `agents/search.py`: a LangGraph model/tools/enrich subgraph
uses `ChatAnthropic`, message state, explicit budgets, and sequential tool replies.
`tools/browser_session.py` keeps sync Playwright on one dedicated thread outside graph state.
The detail tool and enrichment share eligibility rules in `tools/detail_policy.py`.
Search binds static `SEARCH_TOOLS` from `tools/search_tools.py`; definitions are created once
at module import. `SearchContext` supplies the browser, discard keywords, and previous-pass IDs via
the graph's `context_schema` and invocation context. ToolNode supplies hidden ToolRuntime automatically. A sequential adapter invokes
one call at a time and gives the next call the previous call's Command updates. It combines
job/counter/message updates before returning to LangGraph. Listing tools enforce their
budgets before navigation. ToolNode handles dispatch, validation feedback, and unknown-tool
replies; its default handler propagates other tool errors. The browser remains outside state
and the public schemas. There is no separate tool-name registry or manual argument injection.
All four model components define local `ChatPromptTemplate` objects and compose them with
the model using `|`. Search uses `MessagesPlaceholder`; its state excludes the system message
because the template supplies it. Other templates accept named formatted context inputs.
The unused SDK wrapper is removed; Anthropic is supplied transitively by langchain-anthropic.
`coordinator.run` streams task-start and values events; an optional callback sends node
names to the Rich stage display in main.py. Checkpointing and resume are excluded by user
request. Do not introduce them. No graph retries are enabled. The worked example below describes stage
behavior before the graph migration; its coordinator line numbers and loop snippets are historical.

Review improvements: login failure raises `LinkedInAuthenticationError` before report writes.
Enrichment skips jobs with nonblank descriptions and merges only nonblank detail fields.
Model-facing tool validation failures return error ToolMessages for correction within the
existing model-call limit; hidden context and execution errors propagate. Refinement receives
bounded examples/reasons from all match categories and treats configured filters as fixed.
Date, work-mode, and job-type filters stay fixed. SEARCH_LOCATIONS supplies starting
locations rather than an allowlist; refinement can propose new regions. Proposed locations
precede remaining starting locations via config.search_guidance.effective_locations.
Snapshots and reports record that same effective order. Geographic eligibility remains
the matcher's responsibility.
Numeric limits have Pydantic bounds. The coordinator records per-iteration input guidance and
effective settings in `search_params_used`; the writer displays them, without credentials or
profile snapshots. Exact tool calls remain in the trace. Model setup and job formatting use
small shared helpers. A per-model BaseCallbackHandler logs model start/end/error events,
usage, latency, and raw response traces; components no longer invoke the logger explicitly.
Model latency excludes prompt formatting. Prompts, schemas, and parsing stay in their
respective components; output parsing errors are component errors, not model callback errors.

## Current workflow documentation

Use `docs/README.md` as the documentation index. The current graph diagrams and
walkthroughs replace the historical pre-LangGraph example:

- `docs/application-flow.md`: coordinator routing and completion.
- `docs/search-flow.md`: model/tool loop and runtime browser ownership.
- `docs/data-flow.md`: domain objects, component boundaries, and files.
- `docs/refinement-and-search-guidance.md`: validated guidance, direct handoff, and Markdown payload.
- `docs/job-evaluation.md`: employment evidence and shared detail-fetch policy.

## Outputs

| File | Content |
| --- | --- |
| `<run folder>/matched_jobs.md` | All matched jobs, sorted by score, with reasoning |
| `<run folder>/skills_gap.md` | Missing skills grouped by category with priority and frequency |

## LinkedIn login

On first run the browser opens visibly. Log in manually — cookies are saved to `.state/cookies.json` for all subsequent runs.

## Output history

coordinator.run creates `.output/<start-timestamp>_<session-id>/` before graph execution
and configures that folder's trace. PipelineState and SearchSession carry output_dir.
Reports use exclusive creation and the run's start timestamp. Skills-gap reports contain
only the current analysis; prior runs remain in separate folders. Legacy output files
are left untouched. The trace path travels through a ContextVar to graph and browser
workers. This preserves artifacts without checkpointing or resume.

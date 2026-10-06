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

Use the full runtime-planning guide and measurement table in `README.md`. A rough one-iteration
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

### Known quality limitation from the baseline run

LinkedIn's `full-time` metadata may describe weekly commitment rather than the legal engagement.
In the baseline run, six duplicate Gramian postings said `CONTRACT: Contractor assignment` and
`COMMITMENT: Full-time` in their descriptions, but `tools/linkedin.py` extracted `job_type` as
`full-time`. The matcher then incorrectly treated them as permanent employment and skipped them.
Until this is fixed, manually verify high-fit skips where the description contains contractor,
B2B, freelance, interim, or day-rate language. Also note that coordinator deduplication uses only
LinkedIn job ID, so recruiter reposts with different IDs can remain as duplicates.

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
| `.output/matched_jobs.md` | Coordinator after each run |
| `.output/skills_gap.md` | Coordinator after each run |
| `.output/execution_trace.log` | `config/logging.py` — full behind-the-scenes trace (URLs, DOM counts, LLM/tool calls, timings); truncated at the start of every run |

## Agent rules

Do not add tests unless the user explicitly requests them. During this migration, prefer
import, compilation, and lint checks.

Each agent has a strict scope it must never cross:

- **Coordinator** (`agents/coordinator.py`) — runs the pipeline, calls sub-agents. Never scrapes or scores directly.
- **Search Agent** (`agents/search.py`) — scrapes LinkedIn via browser tools. Typed tools and input schemas are defined in `tools/search_tools.py`. Never scores or analyses.
- **Refinement** (`agents/refinement.py`) — recommends search parameters as Markdown. Never scrapes, scores, or writes files; the coordinator persists its output.
- **Matcher Agent** (`agents/matcher.py`) — scores jobs against profile. Never scrapes or browses.
- **Skills Gap Agent** (`agents/skills_gap.py`) — categorises missing skills. Never scrapes or browses.

## Key files

| File | Purpose |
| --- | --- |
| `agents/coordinator.py` | LangGraph orchestration, routing, and persistence |
| `agents/refinement.py` | LangChain search-parameter advice; returns Markdown |
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
edges, and `build_graph()`. See the README migration section for current diagrams and the
learning walkthrough. The CLI return type and existing agent implementations are preserved.
Step 2a is implemented in `agents/skills_gap.py`: `ChatAnthropic` derives structured tool output
from Pydantic response models and converts it to the existing `SkillGap` domain model.
Step 2b is implemented in `agents/matcher.py`: structured Pydantic responses, score bounds,
and exact batch coverage checks (missing/duplicate/unknown IDs). Duplicate input IDs fail
before scoring. Step 2c is implemented in `agents/refinement.py`: the prompt/formatter move
out of the coordinator, and `ChatAnthropic.invoke` returns Markdown. The coordinator saves
it and updates graph state. Step 3 is implemented in `agents/search.py`: a LangGraph model/tools/enrich subgraph
uses `ChatAnthropic`, message state, explicit budgets, and sequential tool replies.
`tools/browser_session.py` keeps sync Playwright on one dedicated thread outside graph state.
Search binds static `SEARCH_TOOLS` from `tools/search_tools.py`; definitions are created once
at module import. `SearchContext` is supplied via the graph's `context_schema` and invocation
context. ToolNode supplies hidden ToolRuntime automatically. A sequential adapter invokes
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
Numeric limits have Pydantic bounds. The coordinator records per-iteration input guidance and
effective settings in `search_params_used`; the writer displays them, without credentials or
profile snapshots. Exact tool calls remain in the trace. Model setup and job formatting use
small shared helpers. A per-model BaseCallbackHandler logs model start/end/error events,
usage, latency, and raw response traces; components no longer invoke the logger explicitly.
Model latency excludes prompt formatting. Prompts, schemas, and parsing stay in their
respective components; output parsing errors are component errors, not model callback errors.

## Pipeline flow (worked example)

This section traces one full run end-to-end, following real data so you can see how
information moves and transforms. File:line references point at the code doing each step.

### The shape of a run

```
main.py
  └─ coordinator.run()                          agents/coordinator.py
       ├─ reader.load_profile / criteria / params
       ├─ for each refinement iteration:
       │    1. search.run()   ── browser + LLM ─▶ list[JobPosting]
       │    2. matcher.run()  ── LLM ───────────▶ list[MatchResult]
       │    3. llm.complete() ── LLM ───────────▶ new search_params.md
       ├─ skills_gap.run()    ── LLM ───────────▶ list[SkillGap]
       └─ writer.save_matched_jobs / save_skills_gap
  └─ display(session)                            config/display.py
```

Data types (`agents/models.py`) flow like this — each stage *enriches* the object:

```
scrape → JobPosting(id,title,company,location,url,easy_apply)
enrich → JobPosting(+description,+salary_range,+work_mode,+job_type,+posted_date)
match  → MatchResult(job, score, matching_skills, missing_skills, match_reason, recommendation)
gaps   → SkillGap(skill, category, frequency, priority)
```

### Example inputs

**`.input/profile.md`** (trimmed):

```markdown
# Ivan — AI & Cloud Engineer
## Skills
Python, AWS (Lambda, Bedrock), LLM/RAG systems, LangChain, LangGraph, Kubernetes (CKAD)
## Experience
10+ yrs backend engineering. Now an AI & Cloud consultant building RAG systems and AI agents.
## Preferences
Remote, contract/freelance, based in the Netherlands.
```

**`.input/search_criteria.md`** (trimmed): keywords `AI Engineer`, `GenAI Engineer`;
locations `Remote`, `Netherlands`; work mode `remote`; job type `contract`; date `past_week`.

**`.input/discard_keywords.txt`**: `frontend, machine learning, qa engineer`

### Stage 0 — startup (`coordinator.py:83-107`)

- `main.py:9` `configure()` truncates `.output/execution_trace.log` and wires logging so every
  event is teed to that file (`config/logging.py`).
- `coordinator.py:84` mints an 8-char `session_id`; `:109` sets a wall-clock `deadline`.
- `reader.load_profile/criteria/params` load the three files. On the **first ever run**
  `.state/search_params.md` is empty, so `:95-101` seeds it from `search_criteria.md` and saves it.
  On later runs it holds the LLM-evolved params from the previous run.

### Stage 1 — search (`coordinator.py:120` → `search.py:run`)

The Search Agent is an **LLM holding two browser tools** (`search.py:24-91`): `scrape_jobs`
and `get_job_details`. The coordinator hands it the params; the LLM decides what to search.

1. **Browser + login** (`search.py:134-141`): launches Chromium, loads `.state/cookies.json`.
   If not logged in → credentials or manual login, then re-saves cookies.
2. **LLM tool loop** (`search.py:222` → `anthropic.py:complete_with_tools`): the model calls
   `scrape_jobs(keywords="AI Engineer", location="Remote", date_posted="past_week", …)`.
   - `on_tool_call` (`search.py:143`) builds the URL (`linkedin.py:build_search_url`):
     `https://www.linkedin.com/jobs/search/?keywords=AI+Engineer&location=Remote&f_TPR=r604800`
   - `scrape_job_listings` (`linkedin.py:272`) pages through results via `&start=0,25,50…`,
     scrolling each page, reading `[data-occludable-job-id]` cards.

   Say LinkedIn returns three cards (note: results are *fuzzy* — not everything is truly AI):

   | id | title | company | easy_apply |
   | --- | --- | --- | --- |
   | 1001 | AI Engineer | Acme | ✔ |
   | 1002 | Frontend Developer | Beta | ✖ |
   | 1003 | Senior ML Engineer | Gamma | ✔ |

   Each becomes a bare `JobPosting` in `jobs_by_id` (`search.py:182-189`).
3. **Enrichment** (`search.py:_enrich_jobs`, `:251`): for every collected job whose **title**
   does *not* contain a discard keyword, fetch its full description.
   - Job **1002 "Frontend Developer"** → title contains `frontend` (a discard keyword) →
     **detail fetch skipped** (`_is_obvious_discard`, `:246`). It stays in the list but with an
     empty description.
   - Jobs 1001 and 1003 → `get_job_details` (`linkedin.py:350`) opens the stable results pane
     `…/jobs/search/?currentJobId=1001`, reads `#job-details` etc., fills in description /
     salary / work_mode / job_type / posted_date. A `JOB_DETAIL_DELAY_MS` pause guards each fetch.

   After enrichment the three `JobPosting`s look like:

   ```
   1001 AI Engineer @ Acme     work_mode=remote  type=contract  desc="…build LLM agents with Python/AWS, RAG pipelines… remote contract…"
   1002 Frontend Developer @ Beta  (no description — title-discarded)
   1003 Senior ML Engineer @ Gamma work_mode=remote type=contract desc="…5+ years experience with machine learning required… PyTorch, model training…"
   ```

4. Back in the coordinator (`:126-136`) new jobs are de-duplicated against prior iterations and
   added to `session.jobs_found`.

### Stage 2 — match (`coordinator.py:138` → `matcher.py:run`)

The Matcher turns each `JobPosting` into a scored `MatchResult`. Two sub-steps:

**2a. Deterministic dealbreaker pre-filter** (`matcher.py:171-194`, no LLM, no tokens):
for each job, `_dealbreaker_hit` scans the **description** for a discard keyword sitting near
requirement language (`years`, `required`, `must have`…).
- Job **1003** description contains *"machine learning required"* → `machine learning` is a
  discard keyword next to `required` → **auto-Skip**, `score=0.0`, reason
  *"Auto-skip: posting hard-requires 'machine learning'…"*, logged `matcher_dealbreaker_skip`.
  It never reaches the LLM.
- Jobs 1001 and 1002 have no such hit → go to the LLM batch (`to_score`).

**2b. LLM scoring** (`matcher.py:196-208` → `anthropic.py:complete_json`): jobs are chunked into
batches of `MATCHER_BATCH_SIZE`. Each batch + the full profile is sent in one forced-tool call
(`submit_matches`). The description shown is truncated to `DESCRIPTION_CHARS = 5000`
(`matcher.py:119`, applied in `format_job` `:122`). The system prompt (`matcher.py:51-68`)
applies **HARD BLOCKERS** first
(non-remote / permanent full-time / location outside NL / frontend-mobile-QA → score 0, Skip),
otherwise scores on skill fit.
- Job **1001 AI Engineer** → remote, contract, LLM/Python/AWS all match the profile → e.g.
  `score=0.9, recommendation="Strong Match", matching_skills=[Python, AWS, LLM/RAG, …]`.
- Job **1002 Frontend Developer** → hard blocker "primarily frontend" fires → `score=0.0,
  recommendation="Skip"`. (Note it was caught twice: title pre-filter skipped its *fetch*, and
  the matcher blocker skips its *score* — belt and braces.)

`_parse` (`matcher.py:145`) maps the returned JSON back onto the `JobPosting`s by `job_id`, and
the results are appended to `session.matched_jobs`.

### Stage 3 — refine (`coordinator.py:143-160`, skipped on the last iteration)

`llm.complete` (plain text, `anthropic.py:complete`) reads a summary of this iteration —
strong matches, top skill gaps, current params, profile excerpt (`_refinement_prompt`,
`coordinator.py:42`) — and **rewrites** `.state/search_params.md` with improved keywords/filters.
A short hint is stored in `session.search_refinements` and fed to the *next* iteration's Search
Agent (`coordinator.py:119`). The loop then repeats Search → Match → Refine until
`MAX_REFINEMENT_ITERATIONS` or the `deadline` is hit.

### Stage 4 — skills gap (`coordinator.py:162` → `skills_gap.py:run`)

Runs **once**, over all `session.matched_jobs`. It collects every `missing_skills` entry across
jobs and sends them to the LLM (`submit_skill_gaps`) to de-duplicate, categorise, count
frequency, and assign priority (High ≥30% of jobs, Medium 10–29%, Low <10%). Output: a list of
`SkillGap`. If job 1001's missing skills were e.g. `Databricks`, that becomes a `SkillGap`.

### Stage 5 — persist (`coordinator.py:166-168` → `config/writer.py`)

- `save_matched_jobs` → **`.output/matched_jobs.md`**: jobs grouped **Strong → Good → Weak →
  Skip**, each sorted by score, each with a collapsible block showing the *exact* `format_job`
  text the matcher saw. Our example: 1001 under **Strong**, 1002 and 1003 under **Skipped**.
- `save_skills_gap` → **`.output/skills_gap.md`**: skills grouped by category as tables; previous
  sessions are appended below.
- `display(session)` (`main.py:26`) prints Rich summary tables to the terminal.

Throughout, every event (URLs, card counts, LLM token/latency, tool calls) and the verbatim LLM
tool inputs/outputs are written to `.output/execution_trace.log` for line-by-line debugging.

## Outputs

| File | Content |
| --- | --- |
| `.output/matched_jobs.md` | All matched jobs, sorted by score, with reasoning |
| `.output/skills_gap.md` | Missing skills grouped by category with priority and frequency |

## LinkedIn login

On first run the browser opens visibly. Log in manually — cookies are saved to `.state/cookies.json` for all subsequent runs.

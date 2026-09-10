# LinkedIn Job Search Agents

A multi-agent pipeline that searches LinkedIn, scores jobs against your profile, and identifies skill gaps — all driven by Claude.

## How it works

```
.input/profile.md          ← your skills & preferences
.input/search_criteria.md  ← what you're looking for
        │
        ▼
  Coordinator (scripted)
  ┌──────────────────────────────────────────────┐
  │  for each iteration:                         │
  │    1. Search Agent  → scrapes LinkedIn jobs  │
  │    2. Matcher Agent → scores jobs 0–1        │
  │    3. LLM refines search params              │
  │  after all iterations:                       │
  │    4. Skills Gap Agent → categorises gaps    │
  └──────────────────────────────────────────────┘
        │
        ▼
.output/matched_jobs.md   ← ranked results with reasoning
.output/skills_gap.md     ← missing skills by category & priority
```

**Search Agent** is an LLM agent with two browser tools (`scrape_jobs`, `get_job_details`). It decides which keyword combinations and filters to try, then drives Playwright to scrape LinkedIn.

**Matcher Agent** is a single LLM call that scores each job 0–1 against your profile and produces `matching_skills`, `missing_skills`, a reason, and a recommendation label.

**Skills Gap Agent** is a single LLM call that aggregates `missing_skills` across all matched jobs, deduplicates them, assigns categories and priorities.

**Coordinator** is scripted (not LLM-driven): it loops search → match → refine, enforces a wall-clock timeout, deduplicates jobs across iterations, and persists outputs.

## Project structure

```
agents/
  coordinator.py   — scripted pipeline + LLM refinement loop
  search.py        — Search Agent (LLM + Playwright browser tools)
  matcher.py       — Matcher Agent (single LLM call, JSON output)
  skills_gap.py    — Skills Gap Agent (single LLM call, JSON output)
  models.py        — JobPosting, MatchResult, SkillGap, SearchSession

tools/
  linkedin.py      — login (cookies → credentials → manual), URL builder, scraper

llm/
  anthropic.py     — Anthropic API wrapper: complete, complete_with_tools, complete_json

config/
  settings.py      — all settings via pydantic-settings + .env
  logging.py       — structlog JSON output
  display.py       — Rich terminal output
  reader.py        — load .input/ and .state/ files into the pipeline
  writer.py        — write results to .state/ and .output/

.input/
  profile.md            — your skills, experience, preferences (edit before first run)
  search_criteria.md    — base search keywords, location, filters

.state/
  search_params.md      — auto-updated each run; evolves from search_criteria.md
  cookies.json          — LinkedIn session cookies (gitignored)

.output/
  matched_jobs.md       — all matches sorted by score with reasoning
  skills_gap.md         — missing skills grouped by category, with history

main.py            — entry point
```

## Setup

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run playwright install chromium   # one-time browser install
```

### Files you must create before the first run

**`.env`** — copy from `.env.example` and set your API key at minimum:
```bash
cp .env.example .env
# Required: ANTHROPIC_API_KEY
```

**`.input/profile.md`** — your skills, experience, and job preferences. The pipeline will fail with an error if this is missing.

**`.input/search_criteria.md`** — keywords, location, and filters for the initial search. The pipeline will fail with an error if this is missing.

### Optional input files

**`.input/discard_keywords.txt`** — comma-separated title keywords that cause a job to be skipped before fetching its full description (e.g. `frontend, ios, android`). If the file is absent, no jobs are discarded by title.

### Auto-generated files (do not create manually)

| File | Created by |
| --- | --- |
| `.state/search_params.md` | Coordinator, after first run — evolves from `search_criteria.md` |
| `.state/cookies.json` | Browser login flow — reused on subsequent runs |
| `.output/matched_jobs.md` | Coordinator, after each run |
| `.output/skills_gap.md` | Coordinator, after each run |

**Run**

```bash
uv run python main.py
```

## Runtime planning

Runtime depends primarily on the number of jobs whose full descriptions are fetched. Search
query count, LinkedIn pagination, matcher batch count, profile/criteria length, and Anthropic
latency are secondary factors.

The Search Agent can make at most:

```text
ceil(MAX_TOTAL_JOBS / MAX_JOBS_PER_SEARCH)
```

`scrape_jobs` calls per iteration. This limits query breadth; `MAX_TOTAL_JOBS` is a cap, not a
promise that the run will collect that many unique jobs.

### Measured runs

The first recorded Agentic AI contract search used the current 1,126-word profile and 898-word
search criteria:

| Date | Search window | Max jobs / per search | Queries | Unique / enriched jobs | Matcher batches | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2026-09-10 | Past month, EU + Netherlands | 30 / 10 | 3 | 20 / 19 | 2 | 179.4 s (2m 59s) |
| 2026-09-10 | Past month, EU + Netherlands | 150 / 20 | 8 | 80 / 74 | 4 | 706.6 s (11m 47s) |

Current observed average: **443.0 seconds (7m 23s) across two successful measured runs**. Because
the runs inspected different numbers of jobs, the pooled end-to-end throughput of **8.9 seconds
per unique job** is more useful than the unweighted run average. Treat both as planning guides,
not guarantees; LinkedIn yield and model latency vary between runs.

Breakdown from `.output/execution_trace.log`:

| Stage | Observed time | Notes |
| --- | ---: | --- |
| Startup, cookie login, initial agent planning | 7.5 s | Existing authenticated cookie, headless browser |
| Three listing searches | 47.4 s | Individual searches took roughly 10–27 s depending on pagination |
| Enrich 19 job descriptions | 93.8 s | 4.9 s/job with `JOB_DETAIL_DELAY_MS=3000` |
| Match 20 jobs in batches of 15 + 5 | 28.6 s | 16,332 input and 2,768 output tokens across both calls |
| Skills-gap analysis and output writing | 2.0 s | One LLM call plus local Markdown writes |

The 80-job run spent 7.5 s on startup, 142.8 s on eight listing searches, 400.1 s enriching 74
descriptions (5.4 s/job), 140.4 s on four 20-job matcher batches, and 15.9 s on skills-gap
analysis/output. It produced 18 Strong, 13 Good, 2 Weak, and 47 Skipped results. Recruiter
reposts with different LinkedIn IDs mean these category counts are not counts of unique roles.

### Estimating a future run

For one search/match iteration, use this rough estimate:

```text
8 seconds startup
+ 10–30 seconds per scrape_jobs call
+ enriched jobs × (JOB_DETAIL_DELAY_MS / 1000 + about 2 seconds browser overhead)
+ 7–45 seconds per matcher batch
+ 2–20 seconds for skills-gap analysis and output
```

For the measured machine and input size, practical planning ranges are:

| Run profile | Suggested settings | Expected time |
| --- | --- | ---: |
| Quick check | 10 total jobs, 10/search, 3 s detail delay, 1 iteration | 1–2 minutes |
| Balanced deep search | 30 total jobs, 10/search, 3 s delay, batch 15, 1 iteration | 3–5 minutes |
| Larger deep search | 45 total jobs, 15/search, 3–4 s delay, batch 15, 1 iteration | 5–8 minutes |
| Broad campaign | 150 total jobs, 20/search, 3 s delay, batch 20, 1 iteration | 15–25 minutes |

Increasing `MAX_REFINEMENT_ITERATIONS` repeats search, enrichment, and matching, so two
iterations can approach twice the single-iteration runtime. `ORCHESTRATOR_TIMEOUT` is a soft
deadline checked between coordinator stages; it cannot interrupt a browser or API call already
in progress, so it should not be treated as a strict process timeout.

To update the average after future runs, record `latency_ms` from the final
`coordinator_complete` event together with query count, unique/enriched jobs, matcher batch size,
and the relevant settings. Comparing runs without those inputs is misleading.

## LinkedIn login

On first run the browser opens visibly. Log in manually — cookies are saved to `.state/cookies.json` for all subsequent runs (headless from then on).

For auto-login, set `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` in `.env`. This may trigger MFA on the first automated attempt.

## Configuration

All settings live in `.env` (copy from `.env.example`). `.env` is the single source of truth — values there always win.

| Variable | Value in `.env.example` | Description |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | required | Anthropic API key |
| `ORCHESTRATOR_MODEL` | `claude-haiku-4-5-20251001` | Model for LLM search-param refinement |
| `SEARCH_MODEL` | `claude-haiku-4-5-20251001` | Model for the Search Agent |
| `MATCHER_MODEL` | `claude-haiku-4-5-20251001` | Model for the Matcher Agent |
| `SKILLS_GAP_MODEL` | `claude-haiku-4-5-20251001` | Model for the Skills Gap Agent |
| `BROWSER_HEADLESS` | `false` | Run browser headlessly (set `true` after first login) |
| `BROWSER_SLOW_MO` | `800` | ms between browser actions (anti-bot detection) |
| `LINKEDIN_EMAIL` | — | Optional: email for auto-login |
| `LINKEDIN_PASSWORD` | — | Optional: password for auto-login |
| `MAX_JOBS_PER_SEARCH` | `20` | Max job cards scraped per `scrape_jobs` call |
| `MAX_TOTAL_JOBS` | `25` | Hard cap on total jobs collected per iteration |
| `JOB_DETAIL_DELAY_MS` | `4000` | Pause between fetching each job detail page |
| `MATCHER_BATCH_SIZE` | `15` | Jobs per matcher LLM call |
| `MATCHER_DESCRIPTION_CHARS` | `7000` | Maximum description characters sent to the matcher per job |
| `MAX_REFINEMENT_ITERATIONS` | `1` | Search → match → refine loops |
| `ORCHESTRATOR_TIMEOUT` | `600.0` | Wall-clock limit for the full session (seconds) |
| `SEARCH_LOCATIONS` | `Remote` | Comma-separated locations the Search Agent should cover |
| `SEARCH_DATE_POSTED` | `past_week` | URL-level recency filter |
| `SEARCH_WORK_MODES` | `remote` | Comma-separated URL-level work-mode filters |
| `SEARCH_JOB_TYPES` | `contract,temporary,part-time` | Comma-separated URL-level job-type filters |

## Development

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
```

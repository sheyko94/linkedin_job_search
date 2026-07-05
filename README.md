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
  client.py        — Anthropic API wrapper: complete, complete_with_tools, extract_json

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
| `JOB_DETAIL_DELAY_MS` | `2000` | Pause between fetching each job detail page |
| `MATCHER_BATCH_SIZE` | `15` | Jobs per matcher LLM call |
| `MAX_REFINEMENT_ITERATIONS` | `1` | Search → match → refine loops |
| `ORCHESTRATOR_TIMEOUT` | `600.0` | Wall-clock limit for the full session (seconds) |

## Development

```bash
uv run ruff check .    # lint
uv run ruff format .   # format
```

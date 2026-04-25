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

No Docker, no database — just Playwright + Anthropic API.

## Configuration (all via Markdown files)

| File | Purpose |
| --- | --- |
| `profiles/profile.md` | Your skills, experience, preferences — edit before first run |
| `profiles/search_criteria.md` | Base search keywords, location, filters — edit to reset search |
| `.state/search_params.md` | Auto-updated by agents each run; evolves from `search_criteria.md` |
| `.state/cookies.json` | LinkedIn session cookies — gitignored, created on first login |

## Agent rules

Each agent has a strict scope it must never cross:

- **Coordinator** (`agents/coordinator.py`) — runs the pipeline, calls sub-agents. Never scrapes or scores directly.
- **Search Agent** (`agents/search.py`) — scrapes LinkedIn via browser tools. Tool schemas (`_TOOLS`) are defined inline. Never scores or analyses.
- **Matcher Agent** (`agents/matcher.py`) — scores jobs against profile. Never scrapes or browses.
- **Skills Gap Agent** (`agents/skills_gap.py`) — categorises missing skills. Never scrapes or browses.

## Key files

| File | Purpose |
| --- | --- |
| `agents/coordinator.py` | Orchestrator — scripted pipeline + LLM refinement loop |
| `agents/search.py` | Search Agent — LLM + Playwright browser tools |
| `agents/matcher.py` | Matcher Agent — single LLM call, JSON output |
| `agents/skills_gap.py` | Skills Gap Agent — single LLM call, JSON output |
| `agents/models.py` | `JobPosting`, `MatchResult`, `SkillGap`, `SearchSession` |
| `browser/linkedin.py` | LinkedIn scraping: login, URL building, job extraction |
| `config/md_loader.py` | Load profile/criteria MD files; write output MD files |
| `config/settings.py` | All settings — mirrored from `.env` |
| `config/logging.py` | structlog JSON configuration |
| `config/display.py` | Rich terminal output |
| `llm/client.py` | Anthropic API wrapper — `complete`, `complete_with_tools`, `extract_json` |

## Outputs

| File | Content |
| --- | --- |
| `output/matched_jobs.md` | All matched jobs, sorted by score, with reasoning |
| `output/skills_gap.md` | Missing skills grouped by category with priority and frequency |

## LinkedIn login

On first run the browser opens visibly. Log in manually — cookies are saved to `.state/cookies.json` for all subsequent runs. Alternatively set `LINKEDIN_EMAIL` + `LINKEDIN_PASSWORD` in `.env` for auto-login (may trigger MFA).

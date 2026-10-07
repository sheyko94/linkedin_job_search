# Configuration

Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`, which is left empty in the
template. The template includes login mode, search size, iteration count, and search filters.
Model names and tuning values have defaults in [config/settings.py](../config/settings.py); add environment
overrides only when needed. Process environment variables override `.env`, which overrides
the code defaults. Optional LinkedIn credentials are unnecessary for manual login or saved cookies.

| Variable | Default / requirement | Description |
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
| `MAX_REFINEMENT_ITERATIONS` | `1` | Maximum search/match passes; refinement runs only between passes |
| `ORCHESTRATOR_TIMEOUT` | `600.0` | Soft deadline for starting searches/refinements (seconds) |
| `SEARCH_LOCATIONS` | `Remote` | Comma-separated starting locations; refinement can propose additional regions |
| `SEARCH_DATE_POSTED` | `past_week` | URL-level recency filter |
| `SEARCH_WORK_MODES` | `remote` | Comma-separated URL-level work-mode filters |
| `SEARCH_JOB_TYPES` | `contract,temporary,part-time` | Comma-separated URL-level job-type filters |
| `OUTPUT_DIR` | `.output` | Parent directory for timestamped run folders |

Job limits, matcher batch size, description length, iteration count, and timeout must be
positive. Timeout must be finite. Browser slowdown and detail delay may be zero, but not
negative. Description length cannot exceed the scraper's 8,000-character cap. Pydantic
checks these constraints when settings load.


[Back to documentation](README.md).

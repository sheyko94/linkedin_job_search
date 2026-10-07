# LinkedIn Job Search Agents

A LangGraph workflow that searches LinkedIn, scores jobs against your profile, and
identifies skill gaps using Claude through LangChain.

## How it works

The coordinator loads your profile and criteria, searches LinkedIn through browser
tools, deduplicates jobs, and matches new postings. If another search pass is allowed,
structured refinement improves the search guidance. Final gap analysis and Markdown
reports complete the run.

`SEARCH_LOCATIONS` supplies starting locations. Refinement can propose new search
regions, which are prioritized in the next pass; candidate eligibility remains unchanged.

- [Application workflow](docs/application-flow.md): coordinator nodes and routing.
- [Search workflow](docs/search-flow.md): model/tool loop and browser lifecycle.
- [Data flow](docs/data-flow.md): inputs, model components, and reports.

Mermaid diagrams render directly on GitHub. The graph does not save interrupted-run
progress or support resume.

## Setup

Requires Python 3.12 or later and `uv`.

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
```

Fill in `ANTHROPIC_API_KEY` in `.env` and create these inputs:

| File | Content |
| --- | --- |
| `.input/profile.md` | Your skills, experience, and preferences |
| `.input/search_criteria.md` | Search keywords and job criteria |
| `.input/discard_keywords.txt` | Optional comma-separated keywords to avoid |

Run the application:

```bash
uv run python main.py
```

The default is one search/match pass, up to 25 collected jobs, with a visible browser.
Set `MAX_REFINEMENT_ITERATIONS=2` or higher to enable refinement between search passes.
See [configuration](docs/configuration.md) for filters, models, and optional overrides,
and [runtime planning](docs/runtime-planning.md) for measured costs and estimates.

## LinkedIn login

Complete login in the visible browser on the first run. Cookies are saved in
`.state/cookies.json` and reused on later runs. Set `BROWSER_HEADLESS=true` once login
works. Optional `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` enable automatic login, which
may require MFA.

Failed authentication stops the run before report writing. The CLI shows login guidance.

## Outputs

Each invocation creates its own folder using the run's start timestamp and session ID:

```text
.output/2026-10-07_08-45-12-123456_a991e836/
  matched_jobs.md
  skills_gap.md
  execution_trace.log
```

Both reports use that same start timestamp. The folder includes microseconds and a
session ID to distinguish runs started close together. The CLI prints its location.

| File | Content |
| --- | --- |
| `<run folder>/matched_jobs.md` | Ranked jobs, scores, reasons, matcher context, and search input snapshots |
| `<run folder>/skills_gap.md` | Missing skills by category and priority for this run |
| `<run folder>/execution_trace.log` | Stage events, model usage, and tool payloads for this run |
| `.state/search_params.md` | Readable search guidance and its validated JSON payload after refinement |

Run folders preserve report and trace history. Failed runs retain their trace; reports
are created only if the workflow reaches report writing. Existing files directly under
`.output` are left untouched. No interrupted-run resume is added.

Existing freeform search-parameter files remain supported. If absent, parameters are
initialized from the base criteria. Refinement updates advice reused by later runs.

## Documentation

Start with the [documentation index](docs/README.md).

- [LangGraph migration walkthrough](docs/langgraph-migration.md): framework responsibilities and code-reading order.
- [Structured refinement](docs/refinement-and-search-guidance.md): schema, validation, direct handoff, and Markdown storage.
- [Job evaluation](docs/job-evaluation.md): contract interpretation and detail-fetch eligibility.

## Development

```bash
uv run ruff check .
uv run ruff format .
```

Tests are added only when explicitly requested.

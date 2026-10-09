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
Model prompts treat the full profile and base criteria as authoritative. See
[prompt policy](docs/prompt-policy.md) for precedence and browser-filter limitations.

- [Application workflow](docs/application-flow.md): coordinator nodes and routing.
- [Search workflow](docs/search-flow.md): model/tool loop and browser lifecycle.
- [Data flow](docs/data-flow.md): inputs, model components, and reports.
- [Generated coordinator](docs/generated/coordinator.md) and
  [generated search graph](docs/generated/search.md): topology exported directly from code.
- [Framework components](docs/framework-components.md): usage accounting, model initialization,
  diagram export, and progress streaming explained step by step.
- [Project structure](docs/project-structure.md): module responsibilities and the simplification walkthrough.

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
| `.input/profile.md` | Candidate facts: skills, experience, residence, work authorization, and languages |
| `.input/search_criteria.md` | Search policy: target roles, requirements, exclusions, rates, and query strategy |
| `.input/discard_keywords.txt` | Optional comma-separated keywords to avoid |

Edit `profile.md` when your experience, skills, or personal circumstances change.
Edit `search_criteria.md` when you want different roles, rates, engagement terms,
or remote requirements. A skill can appear in both: the profile records what you
know; the criteria explains whether that skill matters for this search.
See [input ownership and prompt policy](docs/prompt-policy.md) for how the models use them.

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

Failed authentication stops the run before writing job and skills reports. The CLI shows
login guidance; the run folder retains its trace and any reported token usage.

## Outputs

Each invocation creates its own folder using the run's start timestamp and session ID:

```text
.output/2026-10-07_08-45-12-123456_a991e836/
  matched_jobs.md
  skills_gap.md
  execution_trace.log
  token_usage.json
```

Both reports use that same start timestamp. The folder includes microseconds and a
session ID to distinguish runs started close together. The CLI prints its location.

| File | Content |
| --- | --- |
| `<run folder>/matched_jobs.md` | Ranked jobs, scores, reasons, matcher context, and search input snapshots |
| `<run folder>/skills_gap.md` | Missing skills by category and priority for this run |
| `<run folder>/execution_trace.log` | Stage events, model usage, and tool payloads for this run |
| `<run folder>/token_usage.json` | Provider-reported token totals and per-model details; partial usage on failure |
| `.state/search_guidance.json` | Canonical validated advice loaded on future runs |
| `.state/search_params.md` | Generated readable view of the advice; never read as input |

Run folders preserve report and trace history. Failed runs retain their trace; reports
are created only if the workflow reaches report writing. Existing files directly under
`.output` are left untouched. No interrupted-run resume is added.

If no canonical guidance exists, search uses the base criteria. Refinement creates
advice reused by later runs. Existing structured advice in this checkout has been
migrated to JSON; freeform Markdown is no longer used as search input.

## Documentation

Start with the [documentation index](docs/README.md).

- [LangGraph migration walkthrough](docs/langgraph-migration.md): framework responsibilities and code-reading order.
- [Structured refinement](docs/refinement-and-search-guidance.md): schema, validation, direct handoff, and canonical JSON storage.
- [Job evaluation](docs/job-evaluation.md): contract interpretation and detail-fetch eligibility.

## Development

```bash
uv run ruff check .
uv run ruff format .
```

Tests are added only when explicitly requested.

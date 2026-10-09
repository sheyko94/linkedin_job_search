# Project structure and simplification

The pipeline still loads inputs, searches, deduplicates, matches, optionally refines,
then analyzes skills and writes reports. This refactor reduces duplicated behavior
and gives each module a clear owner.

```text
agents/         workflow, component prompts, shared model client
config/         settings only
domain/         models, engagement evidence, job context, location priorities
tools/          LinkedIn browser operations and typed LangChain tools
storage/        input/advice loading and output writes
presentation/   Rich CLI and pure Markdown report rendering
observability/  logs and raw response traces
scripts/        graph diagram export
```

## Changes in order

1. **Remove unused state.** `JobPosting.requirements` was never populated. Refinement's
   computed-skills-gap branch could never run in the current graph order. Both are
   removed. Refinement history now stores actual `SearchGuidance` objects; the
   redundant notification hint is removed from search prompts and snapshots.
2. **One detail-fetch operation.** `tools/job_details.py` owns eligibility, configured
   delay, fetching, nonblank merge, and engagement extraction. Both explicit tool
   requests and final enrichment call it. `JobDetailError` makes navigation failures
   and missing descriptions visible. Model tools provide error feedback; enrichment
   counts failures and proceeds with other jobs.
3. **One structured-response parser.** `agents/model_client.py` checks LangChain's
   parsing error and expected model type. Matcher keeps its job-ID coverage checks;
   refinement keeps location normalization; skills analysis keeps domain conversion.
   No generic component superclass or agent registry is introduced.
4. **Folders by responsibility.** Models and rules move out of `agents`/`config` into
   `domain`. File operations move to `storage`, CLI and report formatting to
   `presentation`, logs to `observability`. Report rendering returns strings;
   storage chooses paths and writes files.
5. **One source of saved advice.** `.state/search_guidance.json` is canonical and
   validated by Pydantic. `.state/search_params.md` is generated for reading. Search
   and refinement receive the typed guidance directly; duplicate Markdown graph
   state, initial copies of criteria, embedded JSON markers, and runtime legacy
   parsing are removed.

## Where to make a change

| Change | Owner |
| --- | --- |
| Pipeline order or stop conditions | `agents/coordinator.py` |
| Search tool choices or model conversation | `agents/search.py` |
| Matching, refinement, or skills prompts | Corresponding module in `agents/` |
| Model creation, response parsing, call logging | `agents/model_client.py` |
| Candidate/job/guidance data contracts | `domain/models.py` |
| Engagement interpretation or location ordering | `domain/employment.py`, `domain/search_guidance.py` |
| LinkedIn selectors, login, URL extraction | `tools/linkedin.py` |
| Shared detail fetching | `tools/job_details.py` |
| Tool schemas and graph updates | `tools/search_tools.py` |
| File paths and runtime defaults | `config/settings.py` |
| Input loading and output persistence | `storage/reader.py`, `storage/writer.py` |
| Terminal presentation and report formatting | `presentation/cli.py`, `presentation/reports.py` |
| Trace formatting | `observability/logging.py` |

Some complexity remains necessary: the browser thread protects sync Playwright
ownership, the tool adapter applies sequential state updates, and matcher coverage
validation checks that every supplied job gets exactly one result. The two graphs
represent different responsibilities. Removing these would change behavior.

[Back to documentation](README.md).

## Three follow-up review passes

1. **Dependencies:** domain and presentation no longer import settings or storage.
   Report rendering receives the description limit explicitly. The coordinator loads
   discard hints once and passes them to search and matcher, keeping inputs consistent.
2. **State and duplication:** `SearchSnapshot` describes one search pass, and
   `SearchSession.search_history` is a typed list instead of a nested generic dictionary.
   `Settings.listing_call_limit` owns the shared budget formula. The report's safe
   fence formatter also wraps job descriptions that contain Markdown code blocks.
3. **Lifecycle and consistency:** run exit restores previous trace/log contexts on
   success or failure. Required-input loading shares one implementation and rejects
   whitespace-only inputs. Dependency cycles, documentation links, and offline
   pipeline behavior are checked after these changes.

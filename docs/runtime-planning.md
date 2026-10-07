# Runtime planning

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

The first recorded Agentic AI contract search used a 1,126-word profile and 898-word
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


The measurements above predate the shared detail-fetch policy. Current code also skips
IDs processed in earlier passes and applies title-discard rules to explicit tool calls.
Those changes save work when queries overlap; new runtime measurements are needed to
quantify the improvement.

[Detail-fetch policy](job-evaluation.md#detail-fetch-eligibility) · [Documentation index](README.md)

# Data and component flow

The coordinator carries inputs and accumulated results in `PipelineState`. Its
nodes return partial updates; list fields use replacement, so accumulating nodes
return the complete new list. Search history is a typed list of `SearchSnapshot` objects. Domain objects are defined in
[domain/models.py](../domain/models.py).

```mermaid
flowchart LR
    PROFILE[".input/profile.md: candidate facts"] --> READER["storage/reader.py"]
    CRITERIA[".input/search_criteria.md: search policy"] --> READER
    PARAMS[".state/search_guidance.json"] --> READER
    READER --> STATE["PipelineState: inputs and accumulated results"]
    SETTINGS["config/settings.py: environment, .env, defaults"] -.-> SEARCH["Search workflow"]
    SETTINGS -.-> MATCH["Matcher"]
    SETTINGS -.-> REFINE["Refinement"]
    STATE --> SEARCH
    SEARCH --> JOBS["JobPosting: cards plus fetched details"]
    JOBS --> DEDUP["Deduplicate against prior iterations"]
    DEDUP --> MATCH
    PROFILE --> MATCH
    DISCARD[".input/discard_keywords.txt: loaded once"] --> READER
    STATE -.-> MATCH
    MATCH --> RESULTS["MatchResult: job, score, skills, reason, recommendation"]
    RESULTS --> STATE
    STATE --> REFINE
    REFINE --> GUIDANCE["Validated SearchGuidance"]
    GUIDANCE --> STATE
    GUIDANCE --> JSON["storage/writer.py: canonical JSON"]
    JSON --> PARAMS
    GUIDANCE --> MARKDOWN["presentation/reports.py: readable view"]
    MARKDOWN --> VIEW[".state/search_params.md: never read as input"]
    RESULTS --> GAPS["Skills gap analysis after search loop"]
    GAPS --> SKILLS["SkillGap: skill, category, frequency, priority"]
    SKILLS --> STATE
    STATE --> SESSION["SearchSession adapter"]
    SESSION --> WRITER["storage/writer.py"]
    WRITER --> JOBREPORT["Timestamped run folder: matched_jobs.md"]
    WRITER --> GAPREPORT["Timestamped run folder: skills_gap.md"]
    SESSION --> DISPLAY["presentation/cli.py: Rich tables"]
```

Arrows show data dependencies, not execution order. The [application workflow](application-flow.md)
controls when refinement and final analysis run. Paths shown here are defaults;
settings can override them.

## Work inside the model components

```mermaid
flowchart TD
    JOBS["New unique jobs, complete profile and criteria, keyword hints"] --> CHECK["Matcher: validate unique input IDs"]
    CHECK --> BATCH["Split jobs into groups and execute with chain.batch_as_completed"]
    BATCH --> MODEL["ChatPromptTemplate + structured ChatAnthropic"]
    MODEL --> VALIDATE["Pydantic response and exact one-result-per-job coverage"]
    VALIDATE --> MATCHES["Combine validated model results"]
    MATCHES --> ACCUM["Coordinator accumulates MatchResult objects"]
    ACCUM --> REFINE["If another pass is allowed: refinement prompt and structured model call"]
    REFINE --> PARAMS["Validated SearchGuidance returned for direct handoff and JSON storage"]
    ACCUM --> MISSING{"At final analysis: any missing skills?"}
    MISSING -->|No| EMPTY["Return empty gap list without a model call"]
    MISSING -->|Yes| GAPMODEL["Skills gap prompt + structured ChatAnthropic"]
    GAPMODEL --> GAPVALID["Validate Pydantic response and convert to SkillGap objects"]
```

Sources: [matcher.py](../agents/matcher.py), [refinement.py](../agents/refinement.py),
and [skills_gap.py](../agents/skills_gap.py). The matcher and gap analyzer use
`with_structured_output`; their response schemas describe returned data rather
than executable browser tools. Refinement also uses structured output and returns
`SearchGuidance`; see the [refinement walkthrough](refinement-and-search-guidance.md).

Only search chooses and executes tools autonomously. Matching, refinement, and
gap analysis are model-powered workflow steps. LangGraph handles execution and
routing; prompts, budgets, matching rules, browser scraping, and report formatting
remain application code.

## Files and observability

| Data | Lifetime and use |
| --- | --- |
| Profile and criteria | User-maintained inputs loaded for each run |
| Search parameters | Initialized from criteria if blank; replaced after refinement; reused by later runs |
| `.state/cookies.json` | Login cookies reused by the browser, outside graph state |
| Graph states | In-memory run data, with no checkpointing or interrupted-run resume |
| Search input snapshots | Per-iteration guidance and effective filters included in the matched-job report; actual tool calls are in the trace |
| Matched-job report | Created in the timestamped run folder; previous runs are preserved |
| Skills-gap report | This run's analysis in its own folder; no embedded previous-report history |
| Execution trace | Created at run start in the same folder; includes stage events, model usage/latency, and tool payload traces |

The coordinator creates `.output/<start-timestamp>_<session-id>/` before executing
graph nodes. `PipelineState` and `SearchSession` carry its `output_dir`. Logging uses
a context variable for the trace path so graph nodes and the browser worker write
to the same run's trace. Failed runs keep their traces without generating final reports.

[agents/model_client.py](../agents/model_client.py) attaches a LangChain logging
callback to each model. [observability/logging.py](../observability/logging.py) records events and
payloads; [presentation/reports.py](../presentation/reports.py) formats reports;
[storage/writer.py](../storage/writer.py) writes them.

[Back to diagram index](README.md).

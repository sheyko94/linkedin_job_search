# Project documentation

Read these diagrams in order to follow a run from the CLI to the reports:

1. [Application workflow](application-flow.md): coordinator nodes, routing, refinement, and completion.
2. [Search workflow](search-flow.md): the inner model/tool graph, browser ownership, and search limits.
3. [Data and component flow](data-flow.md): input files, domain objects, model calls, and output files.

The diagrams describe the current implementation. Mermaid renders directly on GitHub
and in Markdown viewers with Mermaid support. Rectangles in the workflow diagrams
represent work; diamonds explain conditional routing and are not extra graph nodes.

The [generated coordinator](generated/coordinator.md) and [generated search graph](generated/search.md)
show the exact compiled topology. Refresh them with `uv run python -m scripts.export_graphs`.

## Framework and implementation walkthroughs

- [Project structure](project-structure.md): responsibilities and the ordered simplification walkthrough.

- [LangGraph migration](langgraph-migration.md): framework responsibilities and code-reading order.
- [Structured refinement and search guidance](refinement-and-search-guidance.md): response schema, validation, handoff, and storage.
- [Job evaluation and detail fetching](job-evaluation.md): engagement evidence and shared fetch eligibility.
- [Prompt policy](prompt-policy.md): input authority, generated advice, and execution constraints.
- [Framework components](framework-components.md): token accounting, model initialization, graph exports, and detailed progress.

## Running the application

- [Configuration](configuration.md): environment variables, defaults, and overrides.
- [Runtime planning](runtime-planning.md): measurements and estimates.
- [Quick start](../README.md#setup): installation, input files, and the run command.

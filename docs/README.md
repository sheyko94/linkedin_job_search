# Project documentation

Read these diagrams in order to follow a run from the CLI to the reports:

1. [Application workflow](application-flow.md): coordinator nodes, routing, refinement, and completion.
2. [Search workflow](search-flow.md): the inner model/tool graph, browser ownership, and search limits.
3. [Data and component flow](data-flow.md): input files, domain objects, model calls, and output files.

The diagrams describe the current implementation. Mermaid renders directly on GitHub
and in Markdown viewers with Mermaid support. Rectangles in the workflow diagrams
represent work; diamonds explain conditional routing and are not extra graph nodes.

## Framework and implementation walkthroughs

- [LangGraph migration](langgraph-migration.md): framework responsibilities and code-reading order.
- [Structured refinement and search guidance](refinement-and-search-guidance.md): response schema, validation, handoff, and storage.
- [Job evaluation and detail fetching](job-evaluation.md): engagement evidence and shared fetch eligibility.

## Running the application

- [Configuration](configuration.md): environment variables, defaults, and overrides.
- [Runtime planning](runtime-planning.md): measurements and estimates.
- [Quick start](../README.md#setup): installation, input files, and the run command.

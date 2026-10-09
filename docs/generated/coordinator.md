# Coordinator graph

Generated from the compiled graph. Regenerate from the repository root:

```bash
uv run python -m scripts.export_graphs
```

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	load_inputs(load_inputs)
	search(search)
	deduplicate(deduplicate)
	match(match)
	refine(refine)
	analyze_gaps(analyze_gaps)
	persist(persist)
	__end__([<p>__end__</p>]):::last
	__start__ --> load_inputs;
	analyze_gaps --> persist;
	deduplicate -.-> analyze_gaps;
	deduplicate -.-> match;
	load_inputs -.-> analyze_gaps;
	load_inputs -.-> search;
	match -.-> analyze_gaps;
	match -.-> refine;
	refine -.-> analyze_gaps;
	refine -.-> search;
	search --> deduplicate;
	persist --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc

```

[Back to documentation](../README.md).

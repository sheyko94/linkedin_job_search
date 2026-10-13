"""Refresh graph topology in DEVELOPMENT.md without model or browser calls.

Run from the repository root: uv run python -m scripts.export_graphs
"""

from pathlib import Path

from agents.coordinator import build_graph
from agents.search import build_search_graph


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "DEVELOPMENT.md"
    start_marker = "<!-- BEGIN GENERATED GRAPHS -->"
    end_marker = "<!-- END GENERATED GRAPHS -->"
    original = destination.read_text(encoding="utf-8")
    start = original.index(start_marker) + len(start_marker)
    end = original.index(end_marker, start)
    diagrams = []
    for title, graph in (
        ("Coordinator graph", build_graph()),
        ("Search graph", build_search_graph()),
    ):
        diagrams.append(f"### {title}\n\n```mermaid\n{graph.get_graph().draw_mermaid()}\n```")
    destination.write_text(
        original[:start] + "\n\n" + "\n\n".join(diagrams) + "\n\n" + original[end:],
        encoding="utf-8",
    )
    print("Updated graph diagrams in DEVELOPMENT.md")


if __name__ == "__main__":
    main()

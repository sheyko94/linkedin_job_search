"""Export current graph topology as Markdown without model or browser calls.

Run from the repository root: uv run python -m scripts.export_graphs
"""

from pathlib import Path

from agents.coordinator import build_graph
from agents.search import build_search_graph


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "docs" / "generated"
    destination.mkdir(parents=True, exist_ok=True)
    for name, title, graph in (
        ("coordinator", "Coordinator graph", build_graph()),
        ("search", "Search graph", build_search_graph()),
    ):
        content = (
            f"# {title}\n\n"
            "Generated from the compiled graph. Regenerate from the repository root:\n\n"
            "```bash\nuv run python -m scripts.export_graphs\n```\n\n"
            f"```mermaid\n{graph.get_graph().draw_mermaid()}\n```\n\n"
            "[Back to documentation](../README.md).\n"
        )
        path = destination / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        print(f"Generated {path.relative_to(destination.parents[1])}")


if __name__ == "__main__":
    main()

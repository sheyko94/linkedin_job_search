import argparse
import sys

from config.logging import configure
from config.settings import settings
from agents.coordinator import run
from config.display import console, display


def main() -> None:
    configure()
    parser = argparse.ArgumentParser(description="Multi-agent AI query system")
    parser.add_argument("query", help="The question to answer")
    args = parser.parse_args()

    query = args.query.strip()
    if not query:
        console.print("[bold red]Error:[/bold red] Query cannot be empty.")
        sys.exit(1)
    if len(query) > settings.max_query_length:
        console.print(f"[bold red]Error:[/bold red] Query exceeds maximum length of {settings.max_query_length} characters.")
        sys.exit(1)

    with console.status("[bold blue]Processing…[/bold blue]"):
        try:
            result = run(query)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    display(result)


if __name__ == "__main__":
    main()

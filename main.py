import argparse
import sys

from config.logging import configure
from agents.coordinator import run
from config.display import console, display


def main() -> None:
    configure()
    parser = argparse.ArgumentParser(description="Multi-agent AI query system")
    parser.add_argument("query", help="The question to answer")
    args = parser.parse_args()

    with console.status("[bold blue]Processing…[/bold blue]"):
        try:
            result = run(args.query)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    display(result)


if __name__ == "__main__":
    main()

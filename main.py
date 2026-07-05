import sys

from agents.coordinator import run
from config.display import console, display
from config.logging import configure


def main() -> None:
    configure()

    with console.status("[bold blue]Running LinkedIn job search pipeline…[/bold blue]"):
        try:
            session = run()
        except FileNotFoundError as exc:
            console.print(f"[bold red]Config error:[/bold red] {exc}")
            console.print(
                "\n[dim]Set up your profile by editing:[/dim]\n"
                "  [cyan].input/profile.md[/cyan] — your skills and experience\n"
                "  [cyan].input/search_criteria.md[/cyan] — what jobs to search for"
            )
            sys.exit(1)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            raise

    display(session)


if __name__ == "__main__":
    main()

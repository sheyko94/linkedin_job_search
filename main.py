import sys

from agents.coordinator import run
from config.display import console, display, stage_label
from config.logging import configure
from tools.browser_session import LinkedInAuthenticationError


def main() -> None:
    configure()

    with console.status("[bold blue]Starting LinkedIn job search…[/bold blue]") as status:

        def show_stage(node: str) -> None:
            label = stage_label(node)
            status.update(f"[bold blue]{label}…[/bold blue]")
            console.print(f"[dim]{label}…[/dim]")

        try:
            session = run(on_stage=show_stage)
        except LinkedInAuthenticationError as exc:
            console.print(f"[bold red]LinkedIn login error:[/bold red] {exc}")
            console.print(
                "[dim]Set BROWSER_HEADLESS=false in .env, rerun, and complete "
                "LinkedIn login in the browser. Check LINKEDIN_EMAIL and "
                "LINKEDIN_PASSWORD if using auto-login.[/dim]"
            )
            sys.exit(1)
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

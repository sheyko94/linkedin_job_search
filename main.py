import sys

from agents.coordinator import run
from presentation.cli import console, display, progress_label, stage_label
from tools.browser_session import LinkedInAuthenticationError


def main() -> None:
    with console.status("[bold blue]Starting LinkedIn job search…[/bold blue]") as status:

        def show_stage(node: str) -> None:
            label = stage_label(node)
            status.update(f"[bold blue]{label}…[/bold blue]")
            console.print(f"[dim]{label}…[/dim]")

        def show_progress(event: dict) -> None:
            label = progress_label(event)
            status.update(label)
            console.print(label, style="dim", markup=False)

        try:
            session = run(on_stage=show_stage, on_progress=show_progress)
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

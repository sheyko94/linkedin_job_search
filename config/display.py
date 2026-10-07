from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.models import SearchSession

console = Console()


def stage_label(node: str) -> str:
    """Translate graph node names into terminal progress labels."""
    return {
        "load_inputs": "Loading profile and search criteria",
        "search": "Searching LinkedIn and fetching job descriptions",
        "deduplicate": "Removing jobs already found",
        "match": "Matching jobs against your profile",
        "refine": "Refining search parameters",
        "analyze_gaps": "Analyzing missing skills",
        "persist": "Saving reports",
    }.get(node, node.replace("_", " ").capitalize())


def _score_color(score: float) -> str:
    if score >= 0.75:
        return "green"
    if score >= 0.5:
        return "yellow"
    return "red"


def _rec_style(rec: str) -> str:
    return {
        "Strong Match": "bold green",
        "Good Match": "green",
        "Weak Match": "yellow",
        "Skip": "dim",
    }.get(rec, "white")


def _rec_label(rec: str) -> str:
    return rec.replace(" Match", "")


def display(session: SearchSession) -> None:
    output_dir = Path(session.output_dir)
    # Summary panel
    console.print(
        Panel(
            f"[bold]Session:[/bold] {session.session_id}  "
            f"[bold]Jobs scraped:[/bold] {len(session.jobs_found)}  "
            f"[bold]Matched:[/bold] {len(session.matched_jobs)}  "
            f"[bold]Skill gaps:[/bold] {len(session.skill_gaps)}",
            title=f"LinkedIn Job Search — {session.timestamp}",
            border_style="blue",
        )
    )

    # Matched jobs table (top 20, sorted by score)
    if session.matched_jobs:
        table = Table(title="Job Matches", show_lines=True, border_style="dim")
        table.add_column("Match", style="bold", no_wrap=True)
        table.add_column("Title", max_width=45)
        table.add_column("Missing Skills", max_width=35)
        table.add_column("Link", no_wrap=True)

        sorted_matches = sorted(
            [r for r in session.matched_jobs if r.recommendation != "Skip"],
            key=lambda r: r.score,
            reverse=True,
        )
        skipped = sum(1 for r in session.matched_jobs if r.recommendation == "Skip")
        for r in sorted_matches[:20]:
            color = _score_color(r.score)
            link = r.job.url or "—"
            title = r.job.title
            if r.job.company:
                title += f" [dim]\\[{r.job.company}][/dim]"
            match = (
                f"[{_rec_style(r.recommendation)}]{_rec_label(r.recommendation)}[/]"
                f" - [{color}]{r.score:.0%}[/{color}]"
            )
            table.add_row(
                match,
                title,
                ", ".join(r.missing_skills[:4]) or "—",
                link,
            )
        if not sorted_matches:
            console.print("[yellow]No jobs passed the matcher — all scored 'Skip'.[/yellow]")
        console.print(table)
        if skipped:
            console.print(
                f"[dim]{skipped} job(s) skipped (hard-blocker rules). "
                f"See the 'Skipped' section in {output_dir / 'matched_jobs.md'} for reasons.[/dim]"
            )

    console.print(f"Results saved in {output_dir}", style="dim", markup=False)

    if session.search_refinements:
        console.print(
            f"[dim]Search params updated in .state/search_params.md "
            f"({len(session.search_refinements)} refinement(s) applied)[/dim]"
        )

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.models import SearchSession

console = Console()


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


def display(session: SearchSession) -> None:
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
        table.add_column("Recommendation", style="bold", no_wrap=True)
        table.add_column("Score", justify="right")
        table.add_column("Title", max_width=35)
        table.add_column("Company", max_width=25)
        table.add_column("Location", max_width=20)
        table.add_column("Missing Skills", max_width=35)
        table.add_column("Link", max_width=20)

        sorted_matches = sorted(session.matched_jobs, key=lambda r: r.score, reverse=True)
        for r in sorted_matches[:20]:
            color = _score_color(r.score)
            link = f"[link={r.job.url}]Open[/link]" if r.job.url else "—"
            table.add_row(
                f"[{_rec_style(r.recommendation)}]{r.recommendation}[/]",
                f"[{color}]{r.score:.0%}[/{color}]",
                r.job.title,
                r.job.company,
                r.job.location or "—",
                ", ".join(r.missing_skills[:4]) or "—",
                link,
            )
        console.print(table)

    # Skills gap summary
    if session.skill_gaps:
        gap_table = Table(title="Top Skill Gaps", show_lines=False, border_style="dim")
        gap_table.add_column("Skill", style="cyan")
        gap_table.add_column("Category")
        gap_table.add_column("Jobs", justify="right")
        gap_table.add_column("Priority", justify="center")

        high_gaps = sorted(
            [g for g in session.skill_gaps if g.priority == "High"],
            key=lambda g: g.frequency,
            reverse=True,
        )
        for g in high_gaps[:15]:
            priority_color = "red" if g.priority == "High" else "yellow"
            gap_table.add_row(
                g.skill, g.category, str(g.frequency), f"[{priority_color}]{g.priority}[/{priority_color}]"
            )
        console.print(gap_table)

    console.print("[dim]Results saved to output/matched_jobs.md and output/skills_gap.md[/dim]")

    if session.search_refinements:
        console.print(
            f"[dim]Search params updated in .state/search_params.md "
            f"({len(session.search_refinements)} refinement(s) applied)[/dim]"
        )

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.models import OrchestratedResult

console = Console()


def _confidence_color(c: float) -> str:
    if c >= 0.7:
        return "green"
    if c >= 0.4:
        return "yellow"
    return "red"


def display(result: OrchestratedResult) -> None:
    table = Table(title="Retrieved Evidence", show_lines=True, border_style="dim")
    table.add_column("Chunk ID", style="cyan", no_wrap=True)
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Text", max_width=70)
    for chunk in result.retrieval.chunks:
        table.add_row(chunk.chunk_id, f"{chunk.score:.4f}", chunk.text[:300])
    console.print(table)

    ex = result.execution
    color = _confidence_color(ex.confidence)
    body = ex.answer
    body += f"\n\n[dim]Citations:  {', '.join(ex.citations) or 'none'}[/dim]"
    body += f"\n[dim]Confidence: [{color}]{ex.confidence:.0%}[/{color}][/dim]"
    if ex.missing_information:
        body += "\n[yellow]⚠  Missing information — answer may be incomplete[/yellow]"
    if ex.notes:
        body += f"\n[dim italic]Note: {ex.notes}[/dim italic]"

    console.print(Panel(body, title="Answer", border_style="blue"))
    console.print(f"[dim]Latency: {result.total_latency_ms} ms[/dim]")

"""Write state and output files."""

import json
from pathlib import Path

from config.settings import settings
from domain.models import SearchGuidance, SearchSession
from presentation.reports import render_matched_jobs, render_search_guidance, render_skills_gap


def _write(path: str | Path, content: str, *, overwrite: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w" if overwrite else "x", encoding="utf-8") as file:
        file.write(content)


def save_search_guidance(guidance: SearchGuidance) -> None:
    """Save canonical JSON and a generated Markdown view of the same object."""
    _write(settings.search_guidance_path, guidance.model_dump_json(indent=2) + "\n")
    _write(settings.search_guidance_view_path, render_search_guidance(guidance))


def save_token_usage(output_dir: Path, usage: dict, *, completed: bool) -> None:
    """Save LangChain's per-model usage, including cache detail when reported."""
    totals = {
        key: sum(model.get(key, 0) for model in usage.values())
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    _write(
        output_dir / "token_usage.json",
        json.dumps(
            {"status": "completed" if completed else "failed", "totals": totals, "models": usage},
            indent=2,
        )
        + "\n",
        overwrite=False,
    )


def save_matched_jobs(session: SearchSession) -> None:
    _write(
        Path(session.output_dir) / "matched_jobs.md",
        render_matched_jobs(session, description_chars=settings.matcher_description_chars),
        overwrite=False,
    )


def save_skills_gap(session: SearchSession) -> None:
    _write(Path(session.output_dir) / "skills_gap.md", render_skills_gap(session), overwrite=False)

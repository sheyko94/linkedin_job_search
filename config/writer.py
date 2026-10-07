"""Write state and output files."""

import json
import re
from pathlib import Path

from agents.models import MatchResult, SearchSession, SkillGap
from config.job_formatting import format_job
from config.settings import settings


def _write(path: str | Path, content: str, *, overwrite: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w" if overwrite else "x", encoding="utf-8") as file:
        file.write(content)


def save_search_params(content: str) -> None:
    _write(settings.search_params_path, content)


def _guidance_block(content: str) -> list[str]:
    # Guidance may contain Markdown fences; keep its contents inside this block.
    longest_run = max((len(run) for run in re.findall(r"`+", content)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return [fence, content, fence, ""]


def save_matched_jobs(session: SearchSession) -> None:
    now = session.timestamp
    lines = [
        f"# Matched Jobs — {now}",
        "",
        f"**Session:** `{session.session_id}`  ",
        f"**Jobs scraped:** {len(session.jobs_found)}  ",
        f"**Jobs matched:** {len(session.matched_jobs)}  ",
        "",
    ]

    for snapshot in session.search_params_used.get("iterations", []):
        effective = snapshot["effective_settings"]
        starting_locations = effective.get("starting_locations", effective["locations"])
        lines += [
            "<details><summary><strong>Search Inputs and Effective Filters</strong> "
            f"— iteration {snapshot['iteration']}</summary>",
            "",
            "These are input guidance and effective settings, not exact executed queries. "
            "See the execution trace for actual tool calls.",
            "",
            f"**Configured starting locations:** {', '.join(starting_locations) or '(none)'}  ",
            "**Effective search location order:** "
            f"{', '.join(effective['locations']) or '(none)'}  ",
            f"**Date filter:** {effective['date_posted']}  ",
            f"**Work modes:** {', '.join(effective['work_modes']) or '(no filter)'}  ",
            f"**Job types:** {', '.join(effective['job_types']) or '(no filter)'}  ",
            f"**Max jobs per listing call:** {effective['max_jobs_per_search']}  ",
            f"**Max collected jobs this iteration:** {effective['max_total_jobs']}",
            "",
            "### Search Parameters",
            "",
        ]
        lines += _guidance_block(snapshot["search_params_md"])
        if snapshot.get("search_guidance") is not None:
            lines += ["### Validated Guidance Used by Search", ""]
            lines += _guidance_block(json.dumps(snapshot["search_guidance"], indent=2))
        lines += ["### Base Search Criteria", ""]
        lines += _guidance_block(snapshot["criteria_md"])
        if snapshot["refinement_hint"]:
            lines += ["### Refinement Hint", ""]
            lines += _guidance_block(snapshot["refinement_hint"])
        lines += ["</details>", ""]

    if session.search_refinements:
        lines += ["## Search Refinements for Next Run", ""]
        for r in session.search_refinements:
            lines.append(f"- {r}")
        lines.append("")

    by_rec: dict[str, list[MatchResult]] = {}
    for m in session.matched_jobs:
        by_rec.setdefault(m.recommendation, []).append(m)

    order = ["Strong Match", "Good Match", "Weak Match", "Skip"]
    headings = {"Skip": "Skipped"}
    for rec in order:
        matches = by_rec.get(rec, [])
        if not matches:
            continue
        heading = headings.get(rec, rec.replace(" Match", ""))
        lines += [f"## {heading} ({len(matches)})", ""]
        for m in sorted(matches, key=lambda x: x.score, reverse=True):
            lines += [
                f"### [{m.job.title} @ {m.job.company}]({m.job.url})",
                f"**Score:** {m.score:.0%} | **Location:** {m.job.location} | "
                f"**Mode:** {m.job.work_mode or '—'}",
                f"**Reason:** {m.match_reason}",
                "",
            ]
            if m.matching_skills:
                lines.append(f"**Matching:** {', '.join(m.matching_skills)}")
            if m.missing_skills:
                lines.append(f"**Missing:** {', '.join(m.missing_skills)}")
            lines += [
                "",
                "<details><summary><strong>Context</strong> — exact info the "
                "matcher used</summary>",
                "",
                "```",
                format_job(m.job, description_chars=settings.matcher_description_chars),
                "```",
                "",
                "</details>",
                "",
                "---",
                "",
            ]

    _write(Path(session.output_dir) / "matched_jobs.md", "\n".join(lines), overwrite=False)


def save_skills_gap(session: SearchSession) -> None:
    lines = [
        f"# Skills Gap Analysis — {session.timestamp}",
        "",
        f"_Session: `{session.session_id}`_",
        "",
    ]

    by_category: dict[str, list[SkillGap]] = {}
    for g in session.skill_gaps:
        by_category.setdefault(g.category, []).append(g)

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    for category in sorted(by_category.keys()):
        category_gaps = sorted(
            by_category[category],
            key=lambda g: (priority_order.get(g.priority, 3), -g.frequency),
        )
        lines += [f"## {category}", ""]
        lines.append("| Skill | Frequency | Priority |")
        lines.append("|-------|-----------|----------|")
        for g in category_gaps:
            lines.append(f"| {g.skill} | {g.frequency} jobs | {g.priority} |")
        lines += [""]

    _write(Path(session.output_dir) / "skills_gap.md", "\n".join(lines), overwrite=False)

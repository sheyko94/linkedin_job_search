"""Render reports without reading or writing files."""

import re

from domain.job_formatting import format_job
from domain.models import MatchResult, SearchGuidance, SearchSession, SkillGap


def _code_block(content: str) -> list[str]:
    # Guidance may contain Markdown fences; keep its contents inside this block.
    longest_run = max((len(run) for run in re.findall(r"`+", content)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return [fence, content, fence, ""]


def render_matched_jobs(session: SearchSession, *, description_chars: int) -> str:
    now = session.timestamp
    lines = [
        f"# Matched Jobs — {now}",
        "",
        f"**Session:** `{session.session_id}`  ",
        f"**Jobs scraped:** {len(session.jobs_found)}  ",
        f"**Jobs matched:** {len(session.matched_jobs)}  ",
        "",
    ]

    for snapshot in session.search_history:
        lines += [
            "<details><summary><strong>Search Inputs and Effective Filters</strong> "
            f"— iteration {snapshot.iteration}</summary>",
            "",
            "These are input guidance and effective settings, not exact executed queries. "
            "See the execution trace for actual tool calls.",
            "",
            "**Configured starting locations:** "
            f"{', '.join(snapshot.starting_locations) or '(none)'}  ",
            f"**Effective search location order:** {', '.join(snapshot.locations) or '(none)'}  ",
            f"**Date filter:** {snapshot.date_posted}  ",
            f"**Work modes:** {', '.join(snapshot.work_modes) or '(no filter)'}  ",
            f"**Job types:** {', '.join(snapshot.job_types) or '(no filter)'}  ",
            f"**Max jobs per listing call:** {snapshot.max_jobs_per_search}  ",
            f"**Max collected jobs this iteration:** {snapshot.max_total_jobs}",
            "",
        ]
        if snapshot.guidance is not None:
            lines += ["### Validated Guidance Used by Search", ""]
            lines += _code_block(snapshot.guidance.model_dump_json(indent=2))
        lines += ["### Base Search Criteria", ""]
        lines += _code_block(snapshot.criteria_md)
        lines += ["</details>", ""]

    if session.search_refinements:
        lines += ["## Search Refinements", ""]
        for index, guidance in enumerate(session.search_refinements, start=1):
            lines.append(f"### Refinement {index}")
            lines.append("")
            lines += _code_block(guidance.model_dump_json(indent=2))
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
                *_code_block(format_job(m.job, description_chars=description_chars)),
                "</details>",
                "",
                "---",
                "",
            ]

    return "\n".join(lines)


def render_skills_gap(session: SearchSession) -> str:
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

    return "\n".join(lines)


def render_search_guidance(guidance: SearchGuidance) -> str:
    """Render a view; only search_guidance.json is read by the application."""
    lines = [
        "# Search Parameters",
        "",
        "## Session Insights",
        guidance.insights,
        "",
        "## Keyword Groups (priority order)",
        *[f"- {keywords}" for keywords in guidance.keyword_groups],
        "",
        "## Location Priorities",
        ", ".join(guidance.location_priorities) or "Use configured location order",
        "",
        "## Changes and Reasoning",
        guidance.reasoning,
        "",
        "Generated from search_guidance.json. This Markdown is a view, not application input.",
        "Date, work-mode, and job-type settings remain fixed.",
        "Location proposals are tried before remaining configured starting locations.",
        "",
    ]
    return "\n".join(lines)

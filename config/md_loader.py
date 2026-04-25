"""Load and update markdown configuration and output files."""

from datetime import datetime
from pathlib import Path

from agents.models import MatchResult, SearchSession, SkillGap
from config.settings import settings


def _read(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _write(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def load_profile() -> str:
    content = _read(settings.profile_path)
    if not content:
        raise FileNotFoundError(
            f"Profile not found at '{settings.profile_path}'. "
            "Copy profiles/profile.md.example and fill in your details."
        )
    return content


def load_search_criteria() -> str:
    content = _read(settings.search_criteria_path)
    if not content:
        raise FileNotFoundError(
            f"Search criteria not found at '{settings.search_criteria_path}'. "
            "Copy profiles/search_criteria.md.example and fill in your criteria."
        )
    return content


def load_search_params() -> str:
    """Load evolving search params. Returns empty string if no prior session."""
    return _read(settings.search_params_path)


def save_search_params(content: str) -> None:
    _write(settings.search_params_path, content)


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

    if session.search_refinements:
        lines += ["## Search Refinements for Next Run", ""]
        for r in session.search_refinements:
            lines.append(f"- {r}")
        lines.append("")

    by_rec: dict[str, list[MatchResult]] = {}
    for m in session.matched_jobs:
        by_rec.setdefault(m.recommendation, []).append(m)

    order = ["Strong Match", "Good Match", "Weak Match", "Skip"]
    for rec in order:
        matches = by_rec.get(rec, [])
        if not matches:
            continue
        lines += [f"## {rec} ({len(matches)})", ""]
        for m in sorted(matches, key=lambda x: x.score, reverse=True):
            lines += [
                f"### [{m.job.title} @ {m.job.company}]({m.job.url})",
                f"**Score:** {m.score:.0%} | **Location:** {m.job.location} | **Mode:** {m.job.work_mode or '—'}",
                f"**Reason:** {m.match_reason}",
                "",
            ]
            if m.matching_skills:
                lines.append(f"**Matching:** {', '.join(m.matching_skills)}")
            if m.missing_skills:
                lines.append(f"**Missing:** {', '.join(m.missing_skills)}")
            lines += ["", "---", ""]

    _write(settings.output_jobs_path, "\n".join(lines))


def save_skills_gap(gaps: list[SkillGap], session_id: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# Skills Gap Analysis — {now}",
        "",
        f"_Session: `{session_id}`_",
        "",
    ]

    by_category: dict[str, list[SkillGap]] = {}
    for g in gaps:
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

    existing = _read(settings.output_gaps_path)
    if existing and existing.strip():
        lines += ["---", "", "## Previous Sessions", "", existing]

    _write(settings.output_gaps_path, "\n".join(lines))

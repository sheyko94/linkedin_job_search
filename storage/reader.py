"""Read input and state files."""

from pathlib import Path

from config.settings import settings
from domain.models import SearchGuidance


def read_or_empty(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def _read_required(path: str, label: str) -> str:
    content = read_or_empty(path)
    if not content.strip():
        raise FileNotFoundError(
            f"{label} is missing or blank at '{path}'. Create it and fill in your details."
        )
    return content


def load_profile() -> str:
    return _read_required(settings.profile_path, "Profile")


def load_search_criteria() -> str:
    return _read_required(settings.search_criteria_path, "Search criteria")


def load_discard_keywords() -> set[str]:
    """Returns empty set if file is absent — no jobs are filtered by title."""
    content = read_or_empty(settings.discard_keywords_path)
    if not content.strip():
        return set()
    return {kw.strip().lower() for kw in content.split(",") if kw.strip()}


def load_search_guidance() -> SearchGuidance | None:
    """Read canonical advice; missing is optional, malformed content is an error."""
    path = Path(settings.search_guidance_path)
    return (
        SearchGuidance.model_validate_json(path.read_text(encoding="utf-8"))
        if path.exists()
        else None
    )

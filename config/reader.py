"""Read input and state files."""

from pathlib import Path

from config.settings import settings


def read_or_empty(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def load_profile() -> str:
    content = read_or_empty(settings.profile_path)
    if not content:
        raise FileNotFoundError(
            f"Profile not found at '{settings.profile_path}'. "
            "Create .input/profile.md and fill in your details."
        )
    return content


def load_search_criteria() -> str:
    content = read_or_empty(settings.search_criteria_path)
    if not content:
        raise FileNotFoundError(
            f"Search criteria not found at '{settings.search_criteria_path}'. "
            "Create .input/search_criteria.md and fill in your criteria."
        )
    return content


def load_discard_keywords() -> set[str]:
    """Returns empty set if file is absent — no jobs are filtered by title."""
    content = read_or_empty(settings.discard_keywords_path)
    if not content.strip():
        return set()
    return {kw.strip().lower() for kw in content.split(",") if kw.strip()}


def load_search_params() -> str:
    """Returns empty string if no prior session exists."""
    return read_or_empty(settings.search_params_path)

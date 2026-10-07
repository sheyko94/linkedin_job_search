"""Readable search advice with a validated payload for subsequent runs."""

from agents.models import SearchGuidance
from config.logging import get_logger

logger = get_logger(__name__)

_START = "<!-- search-guidance:v1 -->"
_END = "<!-- /search-guidance -->"


def _unique_locations(locations: list[str]) -> list[str]:
    seen = set()
    unique = []
    for location in locations:
        key = location.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(location)
    return unique


def normalize_locations(guidance: SearchGuidance) -> SearchGuidance:
    """Keep proposed regions, removing only repeated priorities."""
    priorities = _unique_locations(guidance.location_priorities)
    if len(priorities) != len(guidance.location_priorities):
        logger.info("search_guidance_locations_deduplicated", locations=priorities)
    return guidance.model_copy(update={"location_priorities": priorities})


def effective_locations(guidance: SearchGuidance | None, configured: list[str]) -> list[str]:
    """Try proposals first, then append starting locations not already represented."""
    priorities = guidance.location_priorities if guidance is not None else []
    return _unique_locations(priorities + configured)


def render_markdown(guidance: SearchGuidance) -> str:
    """Render human-readable advice and the same object's machine-readable payload."""
    # Fence longer than any backtick run in the payload, including model text.
    payload = guidance.model_dump_json(indent=2)
    fence = "```"
    while fence in payload:
        fence += "`"
    lines = [
        "# Search Parameters",
        "",
        "## Session Insights",
        guidance.insights,
        "",
        "## Keyword Groups (priority order)",
        *[f"- {keywords}" for keywords in guidance.keyword_groups],
        "",
        "## Experience Levels",
        ", ".join(guidance.experience_levels) or "No experience filter",
        "",
        "## Location Priorities",
        ", ".join(guidance.location_priorities) or "Use configured location order",
        "",
        "## Changes and Reasoning",
        guidance.reasoning,
        "",
        "## Structured Guidance",
        "This payload is used by search. Regenerate it through refinement rather than editing",
        "the prose independently. Date, work-mode, and job-type settings remain fixed.",
        "Location proposals are tried before any remaining configured starting locations.",
        "",
        _START,
        f"{fence}json",
        payload,
        fence,
        _END,
        "",
    ]
    return "\n".join(lines)


def parse_markdown(markdown: str) -> SearchGuidance | None:
    """Old freeform documents remain usable; malformed marked payloads fail explicitly."""
    if _START not in markdown:
        return None
    # Use the last marker: model-generated prose may itself contain marker strings.
    block = markdown.rsplit(f"\n{_START}\n", 1)
    if len(block) != 2 or f"\n{_END}" not in block[1]:
        raise ValueError("Saved search guidance has no closing marker")
    lines = block[1].rsplit(f"\n{_END}", 1)[0].strip().splitlines()
    if len(lines) < 3 or not lines[0].startswith("```") or not lines[0].endswith("json"):
        raise ValueError("Saved search guidance has no JSON code block")
    fence = lines[0][:-4]
    if lines[-1] != fence:
        raise ValueError("Saved search guidance has an invalid closing JSON fence")
    return SearchGuidance.model_validate_json("\n".join(lines[1:-1]))

"""Search location priorities, independent of file storage and presentation."""

from domain.models import SearchGuidance


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
    return guidance.model_copy(update={"location_priorities": priorities})


def effective_locations(guidance: SearchGuidance | None, configured: list[str]) -> list[str]:
    """Try proposals first, then append starting locations not already represented."""
    priorities = guidance.location_priorities if guidance is not None else []
    return _unique_locations(priorities + configured)

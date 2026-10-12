"""A minimal hostname guardrail for runtime URLs."""

from urllib.parse import urlsplit

from observability.langfuse import record_guardrail


class URLValidationError(ValueError):
    """The URL does not point to LinkedIn."""


def validate_linkedin_url(url: str) -> str:
    """Allow LinkedIn hosts, record the decision, and reject everything else."""
    try:
        allowed = urlsplit(url).hostname in {"linkedin.com", "www.linkedin.com"}
    except ValueError:
        allowed = False
    record_guardrail(
        "linkedin_url_validation",
        passed=allowed,
        reason="allowed" if allowed else "unapproved_host",
        kind="url",
    )
    if not allowed:
        raise URLValidationError("Only LinkedIn URLs are allowed.")
    return url

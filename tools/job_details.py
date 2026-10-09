"""Shared detail-fetch policy and operation for tools and final enrichment."""

import time
from typing import Any

from config.settings import settings
from domain.employment import engagement_evidence
from domain.models import JobPosting
from observability.logging import get_logger
from tools import linkedin

logger = get_logger(__name__)


def detail_skip_reason(job: JobPosting, previous_job_ids: frozenset[str]) -> str | None:
    if job.id in previous_job_ids:
        return "Job already processed in an earlier search pass; coordinator will deduplicate it."
    if job.description.strip():
        return "Description already collected."
    return None


def fetch_job_details(page: Any, job: JobPosting) -> dict:
    """Delay, fetch and merge on the browser thread; incomplete fetches fail explicitly."""
    try:
        time.sleep(settings.job_detail_delay_ms / 1000)
        details = linkedin.get_job_details(page, job.url)
        for field in ("description", "salary_range", "work_mode", "job_type", "posted_date"):
            value = details.get(field)
            if isinstance(value, str) and value.strip():
                setattr(job, field, value)
        job.engagement_type, job.engagement_evidence = engagement_evidence(
            job.description, job.job_type
        )
        if not job.description.strip():
            raise linkedin.JobDetailError("No job description was returned")
        return details
    except linkedin.JobDetailError as exc:
        logger.warning("job_detail_fetch_failed", job_id=job.id, error=str(exc))
        raise

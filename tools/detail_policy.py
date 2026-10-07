"""One eligibility rule for model-requested details and final enrichment."""

from agents.models import JobPosting


def detail_skip_reason(
    job: JobPosting, discard_keywords: frozenset[str], previous_job_ids: frozenset[str]
) -> str | None:
    if job.id in previous_job_ids:
        return "Job already processed in an earlier search pass; coordinator will deduplicate it."
    if job.description.strip():
        return "Description already collected."
    title = job.title.lower()
    keyword = next((word for word in sorted(discard_keywords) if word in title), None)
    if keyword is not None:
        return f"Title contains configured discard keyword: {keyword}"
    return None

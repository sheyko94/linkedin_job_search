"""Shared job context for model prompts and report provenance."""

from domain.employment import engagement_evidence
from domain.models import JobPosting


def format_job(job: JobPosting, *, description_chars: int) -> str:
    """Render job context with an explicit description limit."""
    lines = [
        f"### Job ID: {job.id}",
        f"Title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location}",
    ]
    if job.work_mode:
        lines.append(f"Work mode: {job.work_mode}")
    if job.job_type:
        lines.append(f"LinkedIn job type / commitment: {job.job_type}")
    # Also cover jobs created before engagement fields were introduced.
    engagement, evidence = job.engagement_type, job.engagement_evidence
    if not evidence:
        engagement, evidence = engagement_evidence(job.description, job.job_type)
    if engagement:
        lines.append(f"Engagement type: {engagement}")
    if evidence:
        lines.append(f"Engagement evidence: {evidence}")
    if job.salary_range:
        lines.append(f"Salary: {job.salary_range}")
    if job.description:
        lines.append(f"Description:\n{job.description[:description_chars]}")
    return "\n".join(lines)

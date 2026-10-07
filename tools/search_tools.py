"""Static tools; ToolNode supplies runtime context and tools return state updates."""

import json
import math
import time
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from agents.models import ExperienceLevel, JobPosting
from config.employment import engagement_evidence
from config.logging import get_logger
from config.settings import settings
from tools import linkedin
from tools.detail_policy import detail_skip_reason
from tools.search_context import SearchContext

logger = get_logger(__name__)


class ScrapeJobsInput(BaseModel):
    keywords: str = Field(description="Job search keywords, e.g. 'senior python engineer'")
    location: str = Field(description="Location string, e.g. 'San Francisco Bay Area' or 'Remote'")
    experience_levels: list[ExperienceLevel] | None = Field(
        default=None, description="Experience level filters"
    )


class JobDetailsInput(BaseModel):
    job_url: str = Field(
        description="Full LinkedIn job URL, e.g. https://www.linkedin.com/jobs/view/1234567890/"
    )


def scrape_jobs(
    keywords: str,
    location: str,
    runtime: ToolRuntime[SearchContext],
    experience_levels: list[str] | None = None,
) -> Command | ToolMessage:
    """Open LinkedIn job search and return job cards for a keyword/location combination.

    Returns a JSON array of cards (id, title, company, location, url, easy_apply).
    Call once per keyword/location combination.
    """
    jobs = {
        job_id: job.model_copy(deep=True) for job_id, job in runtime.state["jobs_by_id"].items()
    }
    scrape_calls = runtime.state["scrape_calls"]
    max_calls = math.ceil(settings.max_total_jobs / settings.max_jobs_per_search)
    if scrape_calls >= max_calls or len(jobs) >= settings.max_total_jobs:
        return ToolMessage(
            content="Search budget reached; no further listing search executed.",
            tool_call_id=runtime.tool_call_id,
            name="scrape_jobs",
        )
    scrape_calls += 1
    url = linkedin.build_search_url(
        keywords=keywords,
        location=location,
        experience_levels=experience_levels,
    )
    remaining = settings.max_total_jobs - len(jobs)
    logger.info(
        "search_tool_scrape_jobs",
        call=scrape_calls,
        keywords=keywords,
        location=location,
        filters={
            "date_posted": settings.search_date_posted,
            "job_types": settings.search_job_types_list,
            "work_modes": settings.search_work_modes_list,
            "experience_levels": experience_levels,
        },
        url=url,
        remaining=remaining,
    )
    cards = [
        card
        for card in runtime.context.browser.call(
            linkedin.scrape_job_listings, url, max_jobs=min(settings.max_jobs_per_search, remaining)
        )
        if card["title"] and card["company"]
    ]
    for card in cards:
        if card["id"] not in jobs:
            try:
                jobs[card["id"]] = JobPosting(
                    id=card["id"],
                    title=card["title"],
                    company=card["company"],
                    location=card["location"],
                    url=card["url"],
                    easy_apply=card["easy_apply"],
                )
            except ValidationError as exc:
                # ToolNode treats ValidationError as invalid model arguments.
                # Invalid scraper data is an execution failure the model cannot fix.
                raise ValueError("LinkedIn scraper returned an invalid job card") from exc
    logger.info(
        "search_tool_scrape_jobs_result", cards_returned=len(cards), total_collected=len(jobs)
    )
    return Command(
        update={
            "jobs_by_id": jobs,
            "scrape_calls": scrape_calls,
            "messages": [
                ToolMessage(
                    content=json.dumps(cards, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id,
                    name="scrape_jobs",
                )
            ],
        }
    )


def _fetch_details(page: Any, job_url: str) -> dict:
    # Delay and navigation both execute on the browser's owning thread.
    time.sleep(settings.job_detail_delay_ms / 1000)
    return linkedin.get_job_details(page, job_url)


def get_job_details(job_url: str, runtime: ToolRuntime[SearchContext]) -> Command | ToolMessage:
    """Fetch full description and metadata for a promising job's LinkedIn URL.

    Be selective — only fetch details for jobs worth evaluating.
    """
    jobs = {
        job_id: job.model_copy(deep=True) for job_id, job in runtime.state["jobs_by_id"].items()
    }
    job = jobs.get(linkedin.job_id_from_url(job_url))
    if job is None:
        return ToolMessage(
            content="Job is not collected. Call scrape_jobs before requesting its details.",
            tool_call_id=runtime.tool_call_id,
            name="get_job_details",
        )
    reason = detail_skip_reason(
        job, runtime.context.discard_keywords, runtime.context.previous_job_ids
    )
    if reason is not None:
        logger.info("search_detail_skipped", job_id=job.id, reason=reason)
        return ToolMessage(
            content=json.dumps({"detail_fetch_skipped": reason, "job": job.model_dump()}),
            tool_call_id=runtime.tool_call_id,
            name="get_job_details",
        )
    logger.info("search_tool_get_job_details", job_url=job_url)
    details = runtime.context.browser.call(_fetch_details, job_url)
    apply_job_details(job, details)
    return Command(
        update={
            "jobs_by_id": jobs,
            "messages": [
                ToolMessage(
                    content=json.dumps(details, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id,
                    name="get_job_details",
                )
            ],
        }
    )


def apply_job_details(job: JobPosting, details: dict) -> None:
    """Merge fetched details without clearing known fields on an incomplete fetch."""
    for field in ("description", "salary_range", "work_mode", "job_type", "posted_date"):
        value = details.get(field)
        if isinstance(value, str) and value.strip():
            setattr(job, field, value)
    job.engagement_type, job.engagement_evidence = engagement_evidence(
        job.description, job.job_type
    )


# Define once. Public schemas contain only model arguments; ToolNode injects runtime.
SEARCH_TOOLS = (
    StructuredTool.from_function(scrape_jobs, args_schema=ScrapeJobsInput),
    StructuredTool.from_function(get_job_details, args_schema=JobDetailsInput),
)

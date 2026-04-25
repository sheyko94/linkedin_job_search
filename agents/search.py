"""Job Search Agent — reads search params, drives LinkedIn browser scraping via tools."""

import json
import math
import time
from typing import Any

from playwright.sync_api import sync_playwright

from agents.models import JobPosting
from browser import linkedin as li
from config.logging import get_logger
from config.settings import settings
from llm import client as llm

logger = get_logger(__name__)


class _LimitReached(Exception):
    pass


_TOOLS = [
    {
        "name": "scrape_jobs",
        "description": (
            "Open LinkedIn job search with the given parameters and scrape job listings. "
            "Returns a JSON array of job cards (id, title, company, location, url, easy_apply). "
            "Call this once per keyword/location combination."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Job search keywords, e.g. 'senior python engineer'",
                },
                "location": {
                    "type": "string",
                    "description": "Location string, e.g. 'San Francisco Bay Area' or 'Remote'",
                },
                "date_posted": {
                    "type": "string",
                    "enum": ["past_day", "past_week", "past_month", "any_time"],
                    "description": "Recency filter for job postings",
                },
                "job_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["full-time", "part-time", "contract", "temporary", "internship"]},
                    "description": "Job type filters",
                },
                "work_modes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["remote", "hybrid", "on-site"]},
                    "description": "Work mode filters",
                },
                "experience_levels": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["entry", "associate", "mid-senior", "director"]},
                    "description": "Experience level filters",
                },
            },
            "required": ["keywords", "location"],
        },
    },
    {
        "name": "get_job_details",
        "description": (
            "Fetch the full job description and metadata for a single job URL. "
            "Use this to enrich jobs that look promising from the listing. "
            "Be selective — only fetch details for jobs worth evaluating."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_url": {
                    "type": "string",
                    "description": "Full LinkedIn job URL, e.g. https://www.linkedin.com/jobs/view/1234567890/",
                },
            },
            "required": ["job_url"],
        },
    },
]

_SYSTEM = """\
You are a LinkedIn job search agent. Your job is to search for and collect job listings \
that match the provided search parameters. You have two tools:

- scrape_jobs: search LinkedIn with keywords, location, and filters
- get_job_details: fetch the full description for a specific job URL

Strategy:
1. Call scrape_jobs with the most relevant keyword combination from the parameters.
2. If the parameters include multiple keyword groups or locations, call scrape_jobs again with variations.
3. Use get_job_details only for jobs where the card info is insufficient to evaluate the role.
4. When you have collected enough jobs (aim for the requested max), stop and summarise what you found.

Never invent job data. Only report what the browser returns.\
"""


def _format_search_params(search_params_md: str, criteria_md: str) -> str:
    return (
        f"## Current Search Parameters\n{search_params_md}\n\n"
        f"## Base Search Criteria\n{criteria_md}\n\n"
        f"Max jobs per search call: {settings.max_jobs_per_search}\n"
        f"Max total jobs to collect across all calls: {settings.max_total_jobs}\n"
        "Stop calling scrape_jobs once you reach the total limit.\n"
        "Use the tools to search LinkedIn and collect job listings now."
    )


def run(
    search_params_md: str,
    criteria_md: str,
    refinement_hint: str = "",
) -> list[JobPosting]:
    """Run the Search Agent. Returns a deduplicated list of JobPosting objects."""

    jobs_by_id: dict[str, JobPosting] = {}
    max_scrape_calls = math.ceil(settings.max_total_jobs / settings.max_jobs_per_search)
    scrape_calls = 0

    with sync_playwright() as pw:
        browser, context = li._create_browser_and_context(pw)
        page = context.new_page()

        try:
            if not li.ensure_logged_in(page, context):
                logger.error("linkedin_login_failed")
                return []

            def on_tool_call(name: str, input: dict) -> str:  # noqa: A002
                nonlocal scrape_calls
                if name == "scrape_jobs":
                    if scrape_calls >= max_scrape_calls or len(jobs_by_id) >= settings.max_total_jobs:
                        raise _LimitReached()
                    url = li.build_search_url(
                        keywords=input["keywords"],
                        location=input["location"],
                        date_posted=input.get("date_posted", "past_week"),
                        job_types=input.get("job_types"),
                        work_modes=input.get("work_modes"),
                        experience_levels=input.get("experience_levels"),
                    )
                    scrape_calls += 1
                    remaining = settings.max_total_jobs - len(jobs_by_id)
                    cards = [
                        c for c in li.scrape_job_listings(page, url, max_jobs=min(settings.max_jobs_per_search, remaining))
                        if c["title"] and c["company"]
                    ]
                    for card in cards:
                        jid = card["id"]
                        if jid not in jobs_by_id and card["title"] and card["company"]:
                            jobs_by_id[jid] = JobPosting(
                                id=jid,
                                title=card["title"],
                                company=card["company"],
                                location=card["location"],
                                url=card["url"],
                                easy_apply=card["easy_apply"],
                            )
                    return json.dumps(cards, ensure_ascii=False)

                if name == "get_job_details":
                    job_url = input["job_url"]
                    time.sleep(settings.job_detail_delay_ms / 1000)
                    details = li.get_job_details(page, job_url)
                    # Find the matching job and enrich it
                    for job in jobs_by_id.values():
                        if job.url == job_url or job.url in job_url:
                            job.description = details["description"]
                            job.salary_range = details["salary_range"]
                            job.work_mode = details["work_mode"]
                            job.job_type = details["job_type"]
                            job.posted_date = details["posted_date"]
                            break
                    return json.dumps(details, ensure_ascii=False)

                return "Unknown tool"

            user_prompt = _format_search_params(search_params_md, criteria_md)
            if refinement_hint:
                user_prompt += f"\n\nRefinement guidance from prior session:\n{refinement_hint}"

            try:
                llm.complete_with_tools(
                    system=_SYSTEM,
                    user=user_prompt,
                    model=settings.search_model,
                    tools=_TOOLS,
                    on_tool_call=on_tool_call,
                    max_tokens=2048,
                    max_iterations=15,
                )
            except _LimitReached:
                logger.info("search_job_limit_reached", total=len(jobs_by_id))

            # Fetch details for jobs not already disqualified by title
            _enrich_jobs(page, jobs_by_id)

        finally:
            context.close()
            browser.close()

    result = list(jobs_by_id.values())
    logger.info("search_agent_complete", total_jobs=len(result))
    return result


_DISCARD_TITLE_KEYWORDS = {
    "frontend", "front-end", "front end", "ios", "android", "mobile",
    "qa engineer", "quality assurance", "test engineer", "us-based", "us only",
    "machine learning", "ml engineer", "ml platform", "data scientist", "data engineer",
    "research scientist", "applied scientist",
}

def _is_obvious_discard(job: JobPosting) -> bool:
    title_lower = job.title.lower()
    return any(kw in title_lower for kw in _DISCARD_TITLE_KEYWORDS)


def _enrich_jobs(page: Any, jobs_by_id: dict[str, JobPosting]) -> None:
    to_fetch = [j for j in jobs_by_id.values() if not _is_obvious_discard(j)]
    logger.info("search_enriching_jobs", total=len(to_fetch))
    for job in to_fetch:
        try:
            time.sleep(settings.job_detail_delay_ms / 1000)
            details = li.get_job_details(page, job.url)
            job.description = details["description"]
            job.salary_range = details["salary_range"]
            job.work_mode = details["work_mode"]
            job.job_type = details["job_type"]
            job.posted_date = details["posted_date"]
        except Exception as e:
            logger.warning("search_enrich_failed", job_id=job.id, error=str(e))

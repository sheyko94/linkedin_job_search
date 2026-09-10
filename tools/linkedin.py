"""LinkedIn browser automation using Playwright.

Handles cookie-based session persistence so the user only needs to log in once.
All browser interaction happens here; agents call these functions as tools.
"""

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# LinkedIn URL helpers
# ---------------------------------------------------------------------------

_DATE_FILTERS = {
    "past_day": "r86400",
    "past_week": "r604800",
    "past_month": "r2592000",
    "any_time": "",
}

_JOB_TYPE_CODES = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
}

_WORK_MODE_CODES = {
    "on-site": "1",
    "remote": "2",
    "hybrid": "3",
}

_EXP_LEVEL_CODES = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}


def build_search_url(
    keywords: str,
    location: str,
    experience_levels: list[str] | None = None,
) -> str:
    params = f"keywords={quote_plus(keywords)}&location={quote_plus(location)}"
    # Recency filter (f_TPR). Authoritative from settings — not LLM-controllable.
    tpr = _DATE_FILTERS.get(settings.search_date_posted, "")
    if tpr:
        params += f"&f_TPR={tpr}"
    # Job-type filter (f_JT). Authoritative from settings; skipped when unset.
    types = settings.search_job_types_list
    if types:
        codes = [_JOB_TYPE_CODES[t] for t in types if t in _JOB_TYPE_CODES]
        if codes:
            params += f"&f_JT={'%2C'.join(codes)}"
    # Work-mode filter (f_WT). Authoritative from settings; skipped when unset.
    modes = settings.search_work_modes_list
    if modes:
        codes = [_WORK_MODE_CODES[m] for m in modes if m in _WORK_MODE_CODES]
        if codes:
            params += f"&f_WT={'%2C'.join(codes)}"
    if experience_levels:
        codes = [_EXP_LEVEL_CODES[e] for e in experience_levels if e in _EXP_LEVEL_CODES]
        if codes:
            params += f"&f_E={'%2C'.join(codes)}"
    return f"https://www.linkedin.com/jobs/search/?{params}"


# ---------------------------------------------------------------------------
# Session / cookie management
# ---------------------------------------------------------------------------


def _load_cookies() -> list[dict] | None:
    p = Path(settings.cookies_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _save_cookies(context: Any) -> None:
    p = Path(settings.cookies_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cookies = context.cookies()
    p.write_text(json.dumps(cookies, indent=2))
    logger.info("linkedin_cookies_saved", path=str(p))


# ---------------------------------------------------------------------------
# Browser context factory
# ---------------------------------------------------------------------------


def _create_browser_and_context(playwright: Any) -> tuple[Any, Any]:
    """Launch Chromium and return (browser, context) with cookies pre-loaded."""
    browser = playwright.chromium.launch(
        headless=settings.browser_headless,
        slow_mo=settings.browser_slow_mo,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    cookies = _load_cookies()
    if cookies:
        context.add_cookies(cookies)
        logger.info("linkedin_cookies_loaded", count=len(cookies))
    return browser, context


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------


def _is_logged_in(page: Any) -> bool:
    """Heuristic: check if the global nav shows the user's profile icon."""
    try:
        page.goto("https://www.linkedin.com/feed/", timeout=15_000)
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        # If redirected to login page we're not logged in
        return "linkedin.com/feed" in page.url or "linkedin.com/in/" in page.url
    except Exception:
        return False


def _login_with_credentials(page: Any) -> bool:
    """Attempt programmatic login. Returns True on success."""
    if not settings.linkedin_email or not settings.linkedin_password:
        return False
    try:
        page.goto("https://www.linkedin.com/login", timeout=15_000)
        page.wait_for_load_state("domcontentloaded")
        page.fill('input[name="session_key"]', settings.linkedin_email)
        page.fill('input[name="session_password"]', settings.linkedin_password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=20_000)
        return "feed" in page.url or "checkpoint" not in page.url
    except Exception as e:
        logger.warning("linkedin_credential_login_failed", error=str(e))
        return False


def _manual_login(page: Any) -> bool:
    """Open browser and wait for user to log in manually."""
    page.goto("https://www.linkedin.com/login", timeout=15_000)
    print(
        "\n[LinkedIn] Browser opened. Please log in manually.\n"
        "The script will continue once you reach your LinkedIn feed.\n"
        "Waiting up to 3 minutes…"
    )
    try:
        # Wait until navigated away from login page (user logged in)
        page.wait_for_url("**/feed/**", timeout=180_000)
        return True
    except Exception:
        return False


def ensure_logged_in(page: Any, context: Any) -> bool:
    """Ensure the browser is authenticated. Tries cookies → credentials → manual."""
    if _is_logged_in(page):
        logger.info("linkedin_session_valid_from_cookies")
        return True
    logger.info("linkedin_not_logged_in_attempting_login")
    if _login_with_credentials(page):
        _save_cookies(context)
        return True
    if _manual_login(page):
        _save_cookies(context)
        return True
    return False


# ---------------------------------------------------------------------------
# Job scraping
# ---------------------------------------------------------------------------


def _safe_text(element: Any) -> str:
    try:
        return element.inner_text().strip()
    except Exception:
        return ""


def _safe_attr(element: Any, attr: str) -> str:
    try:
        return element.get_attribute(attr) or ""
    except Exception:
        return ""


# LinkedIn search results paginate via the &start= URL param, in steps of 25.
_JOBS_PER_PAGE = 25


def _extract_cards_on_page(page: Any, seen_ids: set[str], remaining: int) -> list[dict]:
    """Extract up to `remaining` new job cards currently rendered on the page."""
    collected: list[dict] = []
    cards = page.query_selector_all("[data-occludable-job-id]")
    for card in cards:
        if len(collected) >= remaining:
            break
        job_id = _safe_attr(card, "data-occludable-job-id")
        if not job_id or job_id in seen_ids:
            continue
        # Bring the card into view so its virtualised inner DOM (title/company)
        # renders before we read it — occluded cards otherwise return blank.
        try:
            card.scroll_into_view_if_needed(timeout=3_000)
        except Exception:
            pass
        seen_ids.add(job_id)

        # Extract basic info from card
        title_el = card.query_selector(
            "a.job-card-list__title--link, a[data-control-name='job_card_title']"
        )
        title = _safe_text(title_el) if title_el else ""
        # Always store the canonical individual-job URL for the link column,
        # regardless of the card's actual href (may be a collections/currentJobId link).
        url = f"https://www.linkedin.com/jobs/view/{job_id}/"

        company_el = card.query_selector(
            ".job-card-container__primary-description, "
            ".artdeco-entity-lockup__subtitle, "
            "span.job-card-container__company-name"
        )
        company = _safe_text(company_el) if company_el else ""

        location_el = card.query_selector(
            ".job-card-container__metadata-item, li.job-card-container__metadata-item"
        )
        location = _safe_text(location_el) if location_el else ""

        footer_items = card.query_selector_all(".job-card-container__footer-item")
        footer_text = " ".join(_safe_text(el) for el in footer_items)
        easy_apply = "easy apply" in footer_text.lower()

        collected.append(
            {
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "easy_apply": easy_apply,
            }
        )
    return collected


def scrape_job_listings(page: Any, search_url: str, max_jobs: int) -> list[dict]:
    """Navigate to LinkedIn search URL and extract job cards, paging as needed.

    LinkedIn paginates results via the &start= URL param (0, 25, 50, ...). We walk
    those pages until we have `max_jobs` or a page returns no new results.
    """
    jobs: list[dict] = []
    seen_ids: set[str] = set()
    start = 0

    while len(jobs) < max_jobs:
        page_url = f"{search_url}&start={start}"
        logger.info("linkedin_navigate_search", url=page_url)
        page.goto(page_url, timeout=30_000)
        page.wait_for_load_state("domcontentloaded", timeout=20_000)
        time.sleep(2)

        # The results list scrolls inside its own container (the left pane), so
        # window scrolling does nothing. Scroll the LAST card into view repeatedly
        # to force LinkedIn to render/append all ~25 cards on the page, stopping
        # once the count stabilises.
        prev_count = 0
        for _ in range(15):
            cards = page.query_selector_all("[data-occludable-job-id]")
            if cards:
                try:
                    cards[-1].scroll_into_view_if_needed(timeout=3_000)
                except Exception:
                    pass
            time.sleep(1.0)
            count = len(page.query_selector_all("[data-occludable-job-id]"))
            if count and count == prev_count:
                break
            prev_count = count

        page_jobs = _extract_cards_on_page(page, seen_ids, max_jobs - len(jobs))
        if not page_jobs:
            # No new cards on this page — we've reached the end of results.
            break
        jobs.extend(page_jobs)
        start += _JOBS_PER_PAGE

    logger.info("linkedin_listings_extracted", count=len(jobs))
    return jobs


# The standalone /jobs/view/{id} page now uses randomised, per-deploy class names.
# The search-results DETAIL PANE keeps the stable classic markup and renders the full
# description already expanded (no "show more" click), so we load the job there.
_PANE_URL = "https://www.linkedin.com/jobs/search/?currentJobId={job_id}"

# Description container in the results pane (classic, stable classes).
_DESC_SELECTORS = (
    "#job-details",
    ".jobs-description__content",
    ".jobs-box__html-content",
)

# Top-card metadata pills (work mode / job type / posted date).
_INSIGHT_SELECTORS = (
    ".job-details-jobs-unified-top-card__job-insight, "
    "li.jobs-unified-top-card__job-insight, "
    ".job-details-jobs-unified-top-card__primary-description-container"
)

_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)|currentJobId=(\d+)|/jobPosting/(\d+)")

_MODES = ("remote", "hybrid", "on-site")
_TYPES = ("full-time", "part-time", "contract", "temporary", "internship")


def _job_id_from_url(job_url: str) -> str:
    m = _JOB_ID_RE.search(job_url)
    if not m:
        return ""
    return next(g for g in m.groups() if g)


def _first_text(page: Any, selectors: tuple[str, ...]) -> str:
    """Return the text of the first selector that matches with non-empty content."""
    for sel in selectors:
        el = page.query_selector(sel)
        text = _safe_text(el) if el else ""
        if text:
            return text
    return ""


def get_job_details(page: Any, job_url: str) -> dict:
    """Fetch the full job description + metadata from the stable results-detail pane.

    Note: we load the job via the results-pane URL (currentJobId) because the standalone
    job page is unreliable, but the caller keeps `job.url` as the /jobs/view link.
    """
    empty = dict.fromkeys(
        ("description", "salary_range", "work_mode", "job_type", "posted_date"), ""
    )
    job_id = _job_id_from_url(job_url)
    if not job_id:
        logger.warning("linkedin_job_id_unparsed", url=job_url)
        return empty

    pane_url = _PANE_URL.format(job_id=job_id)
    try:
        page.goto(pane_url, timeout=20_000)
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        try:
            page.wait_for_selector(", ".join(_DESC_SELECTORS), timeout=10_000)
        except Exception:
            time.sleep(1)

        description = _first_text(page, _DESC_SELECTORS)
        salary = _first_text(
            page,
            (".jobs-details__salary-main-rail-card", ".compensation__salary"),
        )

        # Work mode / job type / posted date from the top-card insight pills.
        insights = [_safe_text(el) for el in page.query_selector_all(_INSIGHT_SELECTORS)]
        work_mode = ""
        job_type = ""
        posted_date = ""
        for m in insights:
            m_lower = m.lower()
            if not work_mode and any(x in m_lower for x in _MODES):
                work_mode = next(x for x in _MODES if x in m_lower)
            if not job_type and any(x in m_lower for x in _TYPES):
                job_type = next(x for x in _TYPES if x in m_lower)
            if not posted_date and any(x in m_lower for x in ("ago", "today")):
                posted_date = next(
                    (p.strip() for p in m.split("·") if "ago" in p.lower() or "today" in p.lower()),
                    "",
                )

        # Fall back to scanning title + description text if the pills were absent.
        if not work_mode or not job_type:
            haystack = f"{page.title()} {description}".lower()
            if not work_mode:
                work_mode = next((x for x in _MODES if x in haystack), "")
            if not job_type:
                job_type = next((x for x in _TYPES if x in haystack), "")

        if not description:
            logger.warning("linkedin_job_detail_no_description", url=pane_url)

        return {
            "description": description[:8000],  # cap to avoid huge tokens
            "salary_range": salary,
            "work_mode": work_mode,
            "job_type": job_type,
            "posted_date": posted_date,
        }
    except Exception as e:
        logger.warning("linkedin_job_detail_failed", url=pane_url, error=str(e))
        return empty

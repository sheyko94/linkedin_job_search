"""LinkedIn browser automation using Playwright.

Handles cookie-based session persistence so the user only needs to log in once.
All browser interaction happens here; agents call these functions as tools.
"""

import json
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
    date_posted: str = "past_week",
    job_types: list[str] | None = None,
    work_modes: list[str] | None = None,
    experience_levels: list[str] | None = None,
) -> str:
    params = f"keywords={quote_plus(keywords)}&location={quote_plus(location)}"
    tpr = _DATE_FILTERS.get(date_posted, "r604800")
    if tpr:
        params += f"&f_TPR={tpr}"
    if job_types:
        codes = [_JOB_TYPE_CODES[t] for t in job_types if t in _JOB_TYPE_CODES]
        if codes:
            params += f"&f_JT={'%2C'.join(codes)}"
    if work_modes:
        codes = [_WORK_MODE_CODES[m] for m in work_modes if m in _WORK_MODE_CODES]
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


def scrape_job_listings(page: Any, search_url: str, max_jobs: int) -> list[dict]:
    """Navigate to LinkedIn search URL and extract job cards."""
    logger.info("linkedin_navigate_search", url=search_url)
    page.goto(search_url, timeout=30_000)
    page.wait_for_load_state("domcontentloaded", timeout=20_000)
    time.sleep(2)

    jobs: list[dict] = []
    seen_ids: set[str] = set()
    scroll_attempts = 0
    max_scrolls = 10

    while len(jobs) < max_jobs and scroll_attempts < max_scrolls:
        # Find all job cards on page
        cards = page.query_selector_all("[data-occludable-job-id]")
        for card in cards:
            if len(jobs) >= max_jobs:
                break
            job_id = _safe_attr(card, "data-occludable-job-id")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            # Extract basic info from card
            title_el = card.query_selector("a.job-card-list__title--link, a[data-control-name='job_card_title']")
            title = _safe_text(title_el) if title_el else ""
            url = _safe_attr(title_el, "href") if title_el else ""
            if not url.startswith("http"):
                url = f"https://www.linkedin.com{url}" if url else f"https://www.linkedin.com/jobs/view/{job_id}/"

            company_el = card.query_selector(
                ".job-card-container__primary-description, "
                ".artdeco-entity-lockup__subtitle, "
                "span.job-card-container__company-name"
            )
            company = _safe_text(company_el) if company_el else ""

            location_el = card.query_selector(
                ".job-card-container__metadata-item, "
                "li.job-card-container__metadata-item"
            )
            location = _safe_text(location_el) if location_el else ""

            footer_items = card.query_selector_all(".job-card-container__footer-item")
            footer_text = " ".join(_safe_text(el) for el in footer_items)
            easy_apply = "easy apply" in footer_text.lower()

            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "url": url.split("?")[0],  # strip tracking params
                "easy_apply": easy_apply,
            })

        # Scroll down to load more results
        scroll_attempts += 1
        if len(jobs) < max_jobs:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            # Try clicking "Show more jobs" if present
            show_more = page.query_selector("button.infinite-scroller__show-more-button")
            if show_more:
                try:
                    show_more.click()
                    time.sleep(2)
                except Exception:
                    pass

    logger.info("linkedin_listings_extracted", count=len(jobs))
    return jobs


def get_job_details(page: Any, job_url: str) -> dict:
    """Fetch full job description from the job detail page."""
    try:
        page.goto(job_url, timeout=20_000)
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
        time.sleep(1)

        # Try multiple selectors for description
        desc_el = page.query_selector(
            "#job-details, "
            ".jobs-description__content, "
            ".jobs-box__html-content"
        )
        description = _safe_text(desc_el) if desc_el else ""

        # Try to get salary info
        salary_el = page.query_selector(
            ".compensation__salary, "
            ".jobs-details__salary-main-rail-card"
        )
        salary = _safe_text(salary_el) if salary_el else ""

        # Work mode / job type from top card
        metadata_els = page.query_selector_all(
            ".job-details-jobs-unified-top-card__job-insight, "
            "li.jobs-unified-top-card__job-insight"
        )
        metadata = [_safe_text(el) for el in metadata_els]

        work_mode = ""
        job_type = ""
        posted_date = ""
        for m in metadata:
            m_lower = m.lower()
            if any(x in m_lower for x in ["remote", "hybrid", "on-site"]):
                work_mode = m.split("·")[0].strip()
            if any(x in m_lower for x in ["full-time", "part-time", "contract", "temporary"]):
                job_type = m.split("·")[0].strip()
            if any(x in m_lower for x in ["ago", "today", "hour", "day", "week", "month"]):
                posted_date = m.strip()

        return {
            "description": description[:8000],  # cap to avoid huge tokens
            "salary_range": salary,
            "work_mode": work_mode,
            "job_type": job_type,
            "posted_date": posted_date,
        }
    except Exception as e:
        logger.warning("linkedin_job_detail_failed", url=job_url, error=str(e))
        return {"description": "", "salary_range": "", "work_mode": "", "job_type": "", "posted_date": ""}

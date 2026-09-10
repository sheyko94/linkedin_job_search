from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str
    orchestrator_model: str
    search_model: str
    matcher_model: str
    skills_gap_model: str

    # Browser
    browser_headless: bool
    browser_slow_mo: int
    linkedin_email: str = ""
    linkedin_password: str = ""

    # Scraping
    max_jobs_per_search: int
    max_total_jobs: int
    matcher_batch_size: int
    job_detail_delay_ms: int
    # Description length shown to the matcher. Must be long enough to include the
    # requirements/qualifications block, which usually follows the role intro —
    # truncating too early hides hard requirements and inflates scores. The upstream
    # fetch caps descriptions at 8000 chars.
    matcher_description_chars: int = 5000

    # Pipeline
    max_refinement_iterations: int
    orchestrator_timeout: float

    # Locations to search — one scrape_jobs call per entry. Comma-separated.
    search_locations: str = "Remote"

    # Search filters (URL-level). Configurable — the profile/criteria drive these.
    # Default recency filter (f_TPR): past_day | past_week | past_month | any_time.
    search_date_posted: str = "past_week"
    # Work mode(s) applied to f_WT. Comma-separated: remote | hybrid | on-site.
    # Leave empty to skip the work-mode filter entirely.
    search_work_modes: str = "remote"
    # Job type(s) applied to f_JT. Comma-separated:
    # full-time | part-time | contract | temporary | internship | volunteer.
    # Leave empty to skip the job-type filter entirely.
    search_job_types: str = "contract,temporary,part-time"

    @property
    def search_locations_list(self) -> list[str]:
        return [loc.strip() for loc in self.search_locations.split(",") if loc.strip()]

    @property
    def search_work_modes_list(self) -> list[str]:
        return [m.strip().lower() for m in self.search_work_modes.split(",") if m.strip()]

    @property
    def search_job_types_list(self) -> list[str]:
        return [t.strip().lower() for t in self.search_job_types.split(",") if t.strip()]

    # File paths (internal — not exposed in .env)
    profile_path: str = ".input/profile.md"
    search_criteria_path: str = ".input/search_criteria.md"
    discard_keywords_path: str = ".input/discard_keywords.txt"
    search_params_path: str = ".state/search_params.md"
    cookies_path: str = ".state/cookies.json"
    output_jobs_path: str = ".output/matched_jobs.md"
    output_gaps_path: str = ".output/skills_gap.md"
    trace_path: str = ".output/execution_trace.log"


settings = Settings()

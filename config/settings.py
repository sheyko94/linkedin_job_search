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

    # Pipeline
    max_refinement_iterations: int
    orchestrator_timeout: float

    # Search filters (URL-level). Configurable — the profile/criteria drive these.
    # Default recency filter (f_TPR): past_day | past_week | past_month | any_time.
    search_date_posted: str = "past_week"
    # Work mode(s) applied to f_WT. Comma-separated: remote | hybrid | on-site.
    # Leave empty to skip the work-mode filter entirely.
    search_work_modes: str = "remote"

    @property
    def search_work_modes_list(self) -> list[str]:
        return [m.strip().lower() for m in self.search_work_modes.split(",") if m.strip()]

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

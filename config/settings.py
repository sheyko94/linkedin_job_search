from math import ceil

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-haiku-4-5-20251001"
    search_model: str = "claude-haiku-4-5-20251001"
    matcher_model: str = "claude-haiku-4-5-20251001"
    skills_gap_model: str = "claude-haiku-4-5-20251001"

    # Browser
    browser_headless: bool = False
    browser_slow_mo: int = Field(default=800, ge=0)
    linkedin_email: str = ""
    linkedin_password: str = ""

    # Scraping
    max_jobs_per_search: int = Field(default=20, gt=0)
    max_total_jobs: int = Field(default=25, gt=0)
    matcher_batch_size: int = Field(default=15, gt=0)
    matcher_max_concurrency: int = Field(default=1, gt=0)
    job_detail_delay_ms: int = Field(default=4000, ge=0)
    # Description length shown to the matcher. Must be long enough to include the
    # requirements/qualifications block, which usually follows the role intro —
    # truncating too early hides hard requirements and inflates scores. The upstream
    # fetch caps descriptions at 8000 chars.
    matcher_description_chars: int = Field(default=7000, gt=0, le=8000)

    # Pipeline
    max_refinement_iterations: int = Field(default=1, gt=0)
    orchestrator_timeout: float = Field(default=600.0, gt=0, allow_inf_nan=False)

    # Starting locations, comma-separated. Refinement may propose additional regions.
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
    def listing_call_limit(self) -> int:
        return ceil(self.max_total_jobs / self.max_jobs_per_search)

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
    search_guidance_view_path: str = ".state/search_params.md"
    search_guidance_path: str = ".state/search_guidance.json"
    cookies_path: str = ".state/cookies.json"
    output_dir: str = ".output"


settings = Settings()

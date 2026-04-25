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

    # File paths (internal — not exposed in .env)
    profile_path: str = "profiles/profile.md"
    search_criteria_path: str = "profiles/search_criteria.md"
    search_params_path: str = ".state/search_params.md"
    cookies_path: str = ".state/cookies.json"
    output_jobs_path: str = "output/matched_jobs.md"
    output_gaps_path: str = "output/skills_gap.md"


settings = Settings()

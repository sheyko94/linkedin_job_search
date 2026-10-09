from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SearchGuidance(BaseModel):
    """Adjustable search advice; fixed browser filters are intentionally excluded."""

    model_config = ConfigDict(extra="forbid")

    keyword_groups: list[SearchText] = Field(
        min_length=1,
        max_length=8,
        description="Search keyword combinations, highest priority first",
    )
    location_priorities: list[SearchText] = Field(
        default_factory=list,
        description="Search locations in priority order; may include new regions worth exploring",
    )
    insights: SearchText = Field(description="What successful and rejected matches taught us")
    reasoning: SearchText = Field(description="What changed in the search strategy and why")


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: str
    job_type: str = ""  # full-time, part-time, contract
    engagement_type: str = ""  # contract or permanent, only with explicit evidence
    engagement_evidence: str = ""
    work_mode: str = ""  # remote, hybrid, on-site
    description: str = ""
    url: str
    posted_date: str = ""
    salary_range: str = ""
    easy_apply: bool = False


class MatchResult(BaseModel):
    job: JobPosting
    score: float  # 0.0–1.0
    matching_skills: list[str]
    missing_skills: list[str]
    match_reason: str
    recommendation: str  # "Strong Match" | "Good Match" | "Weak Match" | "Skip"


class SkillGap(BaseModel):
    skill: str
    # category values: "Programming Language" | "Framework" | "Cloud/DevOps" |
    # "Domain Knowledge" | "Soft Skill" | "Other"
    category: str
    frequency: int  # how many jobs in this session require it
    priority: str  # "High" | "Medium" | "Low"


class SearchSnapshot(BaseModel):
    """The guidance and execution settings supplied to one search pass."""

    iteration: int
    criteria_md: str
    guidance: SearchGuidance | None
    starting_locations: list[str]
    locations: list[str]
    date_posted: str
    work_modes: list[str]
    job_types: list[str]
    max_jobs_per_search: int
    max_total_jobs: int


class SearchSession(BaseModel):
    session_id: str
    timestamp: str
    output_dir: str
    search_history: list[SearchSnapshot] = Field(default_factory=list)
    jobs_found: list[JobPosting] = Field(default_factory=list)
    matched_jobs: list[MatchResult] = Field(default_factory=list)
    skill_gaps: list[SkillGap] = Field(default_factory=list)
    search_refinements: list[SearchGuidance] = Field(default_factory=list)
    token_usage: dict[str, dict] = Field(default_factory=dict)

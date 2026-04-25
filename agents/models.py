from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: str
    job_type: str = ""       # full-time, part-time, contract
    work_mode: str = ""      # remote, hybrid, on-site
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    url: str
    posted_date: str = ""
    salary_range: str = ""
    easy_apply: bool = False


class MatchResult(BaseModel):
    job: JobPosting
    score: float             # 0.0–1.0
    matching_skills: list[str]
    missing_skills: list[str]
    match_reason: str
    recommendation: str      # "Strong Match" | "Good Match" | "Weak Match" | "Skip"


class SkillGap(BaseModel):
    skill: str
    category: str            # "Programming Language" | "Framework" | "Cloud/DevOps" | "Domain Knowledge" | "Soft Skill" | "Other"
    frequency: int           # how many jobs in this session require it
    priority: str            # "High" | "Medium" | "Low"


class SearchSession(BaseModel):
    session_id: str
    timestamp: str
    search_params_used: dict
    jobs_found: list[JobPosting] = Field(default_factory=list)
    matched_jobs: list[MatchResult] = Field(default_factory=list)
    skill_gaps: list[SkillGap] = Field(default_factory=list)
    search_refinements: list[str] = Field(default_factory=list)

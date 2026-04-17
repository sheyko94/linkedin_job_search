from pydantic import BaseModel

from search.models import RetrievalResult


class UserTask(BaseModel):
    query: str


class ExecutionResult(BaseModel):
    answer: str
    citations: list[str]
    confidence: float
    missing_information: bool = False
    notes: str | None = None


class OrchestratedResult(BaseModel):
    query: str
    retrieval: RetrievalResult
    execution: ExecutionResult
    total_latency_ms: int

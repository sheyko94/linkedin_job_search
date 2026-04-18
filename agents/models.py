from pydantic import BaseModel

from opensearch.models import RetrievalResult


class AnswerResult(BaseModel):
    answer: str
    citations: list[str]
    confidence: float
    missing_information: bool = False
    notes: str | None = None


class QueryResult(BaseModel):
    query: str
    retrieval: RetrievalResult
    execution: AnswerResult
    total_latency_ms: int

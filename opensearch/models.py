from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk]

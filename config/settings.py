from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    orchestrator_model: str = "claude-sonnet-4-6"
    research_model: str = "claude-haiku-4-5-20251001"
    answer_model: str = "claude-haiku-4-5-20251001"
    retrieval_top_k: int = 5
    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "docs"
    opensearch_timeout: float = 2.0
    max_attempts: int = 3
    max_search_iterations: int = 10
    orchestrator_timeout: float = 60.0
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 3
    reranker_enabled: bool = True
    max_query_length: int = 2000


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"
    retrieval_top_k: int = 5
    opensearch_url: str = "http://localhost:9200"
    opensearch_index: str = "docs"


settings = Settings()

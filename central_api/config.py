from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


EmbeddingProvider = Literal["local", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")

    database_url: str

    # Embedding provider selection. "local" is the default and uses sentence-transformers.
    # "openai" is opt-in and requires openai_api_key + DB schema with vector(1536).
    embedding_provider: EmbeddingProvider = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # Only required when embedding_provider == "openai".
    openai_api_key: str | None = None

    api_host: str = "0.0.0.0"
    api_port: int = 8080


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

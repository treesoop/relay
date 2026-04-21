from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RELAY_", env_file=".env", extra="ignore")

    database_url: str
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    api_host: str = "0.0.0.0"
    api_port: int = 8080


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

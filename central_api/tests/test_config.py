import pytest

from central_api.config import Settings


def test_settings_loads_defaults(monkeypatch):
    monkeypatch.delenv("RELAY_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.openai_api_key == "sk-test"
    assert s.embedding_model == "text-embedding-3-small"
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8080


def test_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("RELAY_DATABASE_URL", raising=False)
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk")
    with pytest.raises(Exception):  # pydantic-settings raises ValidationError
        Settings()

import pytest

from central_api.config import Settings


def test_settings_loads_defaults(monkeypatch):
    # Clear all optional envs so defaults kick in.
    for key in ("RELAY_EMBEDDING_PROVIDER", "RELAY_EMBEDDING_MODEL",
                "RELAY_EMBEDDING_DIM", "RELAY_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.embedding_provider == "local"
    assert s.embedding_model == "BAAI/bge-small-en-v1.5"
    assert s.embedding_dim == 384
    assert s.openai_api_key is None
    assert s.api_host == "0.0.0.0"
    assert s.api_port == 8080


def test_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("RELAY_DATABASE_URL", raising=False)
    with pytest.raises(Exception):
        Settings()


def test_settings_openai_provider_allows_key(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")

    s = Settings()
    assert s.embedding_provider == "openai"
    assert s.openai_api_key == "sk-test"


def test_settings_invalid_provider_rejected(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "bogus")
    with pytest.raises(Exception):
        Settings()

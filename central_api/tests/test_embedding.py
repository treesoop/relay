import pytest

from central_api.config import Settings
from central_api.embedding import (
    EmbeddingClient,
    LocalEmbedder,
    OpenAIEmbedder,
    StubEmbedder,
    build_embedder,
    build_embedding_targets,
)


def test_build_embedding_targets():
    metadata = {
        "problem": {"symptom": "429 under burst", "context": "checkout"},
        "solution": {"approach": "backoff", "tools_used": [{"type": "library", "name": "tenacity"}]},
        "attempts": [
            {"tried": "retry loop", "failed_because": "no Retry-After"},
            {"worked": "backoff"},
        ],
    }
    targets = build_embedding_targets(
        description="Handle Stripe 429 with backoff",
        metadata=metadata,
    )
    assert targets["description"].startswith("Handle Stripe 429")
    assert "429 under burst" in targets["problem"]
    assert "checkout" in targets["problem"]
    assert "backoff" in targets["solution"]
    assert "tenacity" in targets["solution"]
    assert "retry loop" in targets["solution"]


@pytest.mark.asyncio
async def test_stub_embedder_default_dim_is_384():
    stub = StubEmbedder()
    v = await stub.embed("x")
    assert len(v) == 384


@pytest.mark.asyncio
async def test_stub_embedder_custom_dim():
    stub = StubEmbedder(dim=1536)
    v = await stub.embed("x")
    assert len(v) == 1536


@pytest.mark.asyncio
async def test_stub_embedder_deterministic():
    stub = StubEmbedder()
    v1 = await stub.embed("same")
    v2 = await stub.embed("same")
    v3 = await stub.embed("different")
    assert v1 == v2
    assert v1 != v3


@pytest.mark.asyncio
async def test_stub_embedder_batch():
    stub = StubEmbedder()
    vectors = await stub.embed_many(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)


@pytest.mark.asyncio
async def test_local_embedder_smoke():
    """Actual end-to-end with sentence-transformers. Slow (downloads model on first run).

    If the test machine has no disk/network for the model, this will raise.
    We accept the slowness — it's the only integration check for the real embedder.
    """
    emb = LocalEmbedder(model_name="BAAI/bge-small-en-v1.5")
    v = await emb.embed("hello world")
    assert len(v) == 384
    assert all(isinstance(x, float) for x in v)

    batch = await emb.embed_many(["alpha", "beta"])
    assert len(batch) == 2
    assert all(len(x) == 384 for x in batch)


def test_build_embedder_local_by_default(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    for key in ("RELAY_EMBEDDING_PROVIDER", "RELAY_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    emb = build_embedder(settings)
    assert isinstance(emb, LocalEmbedder)


def test_build_embedder_openai_when_configured(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("RELAY_OPENAI_API_KEY", "sk-test")
    settings = Settings()
    emb = build_embedder(settings)
    assert isinstance(emb, OpenAIEmbedder)


def test_build_embedder_openai_without_key_raises(monkeypatch):
    monkeypatch.setenv("RELAY_DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("RELAY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("RELAY_OPENAI_API_KEY", raising=False)
    settings = Settings()
    with pytest.raises(ValueError, match="openai_api_key"):
        build_embedder(settings)

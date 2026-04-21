import pytest

from central_api.embedding import EmbeddingClient, StubEmbedder, build_embedding_targets


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
    # Attempts summary included in solution text
    assert "retry loop" in targets["solution"]


@pytest.mark.asyncio
async def test_stub_embedder_returns_deterministic_vectors():
    stub = StubEmbedder(dim=1536)
    v1 = await stub.embed("same text")
    v2 = await stub.embed("same text")
    v3 = await stub.embed("different")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 1536
    assert all(isinstance(x, float) for x in v1)


@pytest.mark.asyncio
async def test_stub_embedder_batch():
    stub = StubEmbedder(dim=1536)
    vectors = await stub.embed_many(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 1536 for v in vectors)

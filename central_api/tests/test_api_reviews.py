import pytest
from httpx import AsyncClient, ASGITransport

from central_api.db import get_session
from central_api.embedding import StubEmbedder
from central_api.main import create_app


@pytest.fixture
def app(db_session):
    app = create_app(embedder=StubEmbedder())

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    return app


async def _register(client: AsyncClient, agent_id: str) -> dict[str, str]:
    r = await client.post("/auth/register", json={"agent_id": agent_id})
    return {"X-Relay-Agent-Id": agent_id, "X-Relay-Agent-Secret": r.json()["secret"]}


async def _seed_skill(client: AsyncClient, agent: str = "uploader") -> str:
    headers = await _register(client, agent)
    r = await client.post("/skills", json={
        "name": "r-skill", "description": "d", "when_to_use": "w", "body": "b",
        "metadata": {
            "problem": {"symptom": "x"},
            "solution": {"approach": "y", "tools_used": []},
            "attempts": [],
            "context": {"languages": [], "libraries": []},
        },
    }, headers=headers)
    return r.json()["id"]


@pytest.mark.asyncio
async def test_post_review_good_updates_counts(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        reviewer_headers = await _register(client, "reviewer")

        r = await client.post(f"/skills/{sid}/reviews", json={"signal": "good"},
                              headers=reviewer_headers)
        assert r.status_code == 201, r.text

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "reviewer"})).json()
        assert s["good_count"] == 1
        assert s["bad_count"] == 0
        # confidence = (1 + 0.5) / (1 + 0 + 1) = 0.75
        assert abs(s["confidence"] - 0.75) < 1e-6


@pytest.mark.asyncio
async def test_post_review_bad_updates_counts(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        reviewer_headers = await _register(client, "reviewer")

        r = await client.post(f"/skills/{sid}/reviews",
                              json={"signal": "bad", "reason": "api_changed"},
                              headers=reviewer_headers)
        assert r.status_code == 201

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "reviewer"})).json()
        assert s["good_count"] == 0
        assert s["bad_count"] == 1
        # (0 + 0.5) / (0 + 1 + 1) = 0.25
        assert abs(s["confidence"] - 0.25) < 1e-6


@pytest.mark.asyncio
async def test_three_stale_reviews_flip_status(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        for agent in ("r1", "r2", "r3"):
            h = await _register(client, agent)
            r = await client.post(f"/skills/{sid}/reviews", json={"signal": "stale"}, headers=h)
            assert r.status_code == 201

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "r1"})).json()
        assert s["status"] == "stale"


@pytest.mark.asyncio
async def test_stale_skill_excluded_from_search(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        for agent in ("r1", "r2", "r3"):
            h = await _register(client, agent)
            await client.post(f"/skills/{sid}/reviews", json={"signal": "stale"}, headers=h)

        r = await client.get("/skills/search",
                             params={"query": "x", "search_mode": "problem"},
                             headers={"X-Relay-Agent-Id": "r1"})
        items = r.json()["items"]
        assert all(it["skill"]["id"] != sid for it in items)


@pytest.mark.asyncio
async def test_invalid_signal_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        h = await _register(client, "r")
        r = await client.post(f"/skills/{sid}/reviews", json={"signal": "bogus"}, headers=h)
        assert r.status_code == 422  # pydantic rejects enum value


@pytest.mark.asyncio
async def test_review_on_missing_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = await _register(client, "r")
        r = await client.post("/skills/sk_nope/reviews", json={"signal": "good"}, headers=h)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_review_without_secret_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        await client.post("/auth/register", json={"agent_id": "r"})
        r = await client.post(f"/skills/{sid}/reviews", json={"signal": "good"},
                              headers={"X-Relay-Agent-Id": "r"})
        assert r.status_code == 401

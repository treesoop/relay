import pytest
from httpx import AsyncClient, ASGITransport

from central_api.db import get_session
from central_api.embedding import StubEmbedder
from central_api.main import create_app


@pytest.fixture
def app(db_session):
    """App with stubbed embedder + session-injected DB."""
    app = create_app(embedder=StubEmbedder())

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    return app


@pytest.mark.asyncio
async def test_post_skills_masks_pii_and_stores(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register agent first
        await client.post("/auth/register", json={"agent_id": "uploader"})
        headers = {"X-Relay-Agent-Id": "uploader"}

        payload = {
            "name": "stripe-429",
            "description": "Handle Stripe 429 with backoff",
            "when_to_use": "When Stripe returns 429",
            "body": "alice@example.com debugged this; key=sk-proj-abcdefghijklmnopqrstuvwx1234567890",
            "metadata": {
                "problem": {"symptom": "429 burst", "context": "checkout"},
                "solution": {
                    "approach": "backoff",
                    "tools_used": [{"type": "library", "name": "tenacity"}],
                },
                "attempts": [
                    {"tried": "retry loop", "failed_because": "ignored Retry-After"},
                    {"worked": "backoff"},
                ],
                "context": {"languages": ["python"], "libraries": ["stripe-python"]},
            },
        }

        r = await client.post("/skills", json=payload, headers=headers)
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["id"].startswith("sk_")
        assert data["name"] == "stripe-429"
        assert "alice@example.com" not in data["body"]
        assert "[REDACTED:email]" in data["body"]
        assert "sk-proj-" not in data["body"]
        assert data["source_agent_id"] == "uploader"


@pytest.mark.asyncio
async def test_post_skills_rejects_without_header(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/skills", json={
            "name": "x", "description": "d", "when_to_use": "w",
            "body": "b", "metadata": {},
        })
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_skill_roundtrip(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "u"})
        headers = {"X-Relay-Agent-Id": "u"}

        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "hi",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=headers)
        sid = post.json()["id"]

        r = await client.get(f"/skills/{sid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["id"] == sid
        assert r.json()["body"] == "hi"


@pytest.mark.asyncio
async def test_get_missing_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "u"})
        r = await client.get("/skills/sk_does_not_exist", headers={"X-Relay-Agent-Id": "u"})
        assert r.status_code == 404

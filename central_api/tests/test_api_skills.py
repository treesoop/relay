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


async def _register(client: AsyncClient, agent_id: str) -> dict[str, str]:
    """Register and return headers with both id + secret."""
    r = await client.post("/auth/register", json={"agent_id": agent_id})
    secret = r.json()["secret"]
    return {"X-Relay-Agent-Id": agent_id, "X-Relay-Agent-Secret": secret}


@pytest.mark.asyncio
async def test_post_skills_masks_pii_and_stores(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register(client, "uploader")

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
async def test_post_skills_rejects_without_secret(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "uploader"})
        r = await client.post("/skills", json={
            "name": "x", "description": "d", "when_to_use": "w",
            "body": "b", "metadata": {},
        }, headers={"X-Relay-Agent-Id": "uploader"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_skill_roundtrip(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register(client, "u")

        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "hi",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=headers)
        sid = post.json()["id"]

        # GET is loose: only id header needed.
        r = await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "u"})
        assert r.status_code == 200
        assert r.json()["id"] == sid
        assert r.json()["body"] == "hi"


@pytest.mark.asyncio
async def test_get_missing_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _register(client, "u")
        r = await client.get("/skills/sk_does_not_exist", headers={"X-Relay-Agent-Id": "u"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_skill_owner_can_update(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register(client, "author")

        post = await client.post("/skills", json={
            "name": "foo", "description": "old desc", "when_to_use": "w", "body": "old body",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=headers)
        sid = post.json()["id"]

        patch = await client.patch(f"/skills/{sid}", json={
            "description": "new pushy desc",
            "body": "new body",
        }, headers=headers)
        assert patch.status_code == 200, patch.text
        data = patch.json()
        assert data["description"] == "new pushy desc"
        assert data["body"] == "new body"
        assert data["id"] == sid  # same id


@pytest.mark.asyncio
async def test_patch_skill_non_owner_forbidden(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        author_headers = await _register(client, "author")
        intruder_headers = await _register(client, "intruder")

        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "b",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=author_headers)
        sid = post.json()["id"]

        r = await client.patch(f"/skills/{sid}", json={"description": "hijack"},
                               headers=intruder_headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_skill_owner_can_delete(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register(client, "author")
        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "b",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=headers)
        sid = post.json()["id"]

        r = await client.delete(f"/skills/{sid}", headers=headers)
        assert r.status_code == 204

        got = await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "author"})
        assert got.status_code == 404


@pytest.mark.asyncio
async def test_delete_skill_non_owner_forbidden(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        author_headers = await _register(client, "author")
        intruder_headers = await _register(client, "intruder")
        post = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w", "body": "b",
            "metadata": {
                "problem": {"symptom": "s"},
                "solution": {"approach": "a", "tools_used": []},
            },
        }, headers=author_headers)
        sid = post.json()["id"]

        r = await client.delete(f"/skills/{sid}", headers=intruder_headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_body_exceeding_cap_rejected_422(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _register(client, "u")
        r = await client.post("/skills", json={
            "name": "foo", "description": "d", "when_to_use": "w",
            "body": "x" * 60_000,
            "metadata": {},
        }, headers=headers)
        assert r.status_code == 422

import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport

from central_api.auth import require_agent_id, require_authenticated_agent
from central_api.db import get_session
from central_api.routers.auth_router import router as auth_router


def _build_app(db_session):
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(agent_id: str = Depends(require_agent_id)):
        return {"agent_id": agent_id}

    @app.get("/secure-whoami")
    async def secure(agent_id: str = Depends(require_authenticated_agent)):
        return {"agent_id": agent_id}

    app.include_router(auth_router)

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    return app


@pytest.mark.asyncio
async def test_whoami_requires_header(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_whoami_reads_header(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami", headers={"X-Relay-Agent-Id": "pseudo_xyz"})
        assert r.status_code == 200
        assert r.json() == {"agent_id": "pseudo_xyz"}


@pytest.mark.asyncio
async def test_register_issues_secret_once(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/auth/register", json={"agent_id": "new_pseudo"})
        assert r1.status_code == 201
        body1 = r1.json()
        assert body1["agent_id"] == "new_pseudo"
        assert body1["secret"] and isinstance(body1["secret"], str)

        # Second call for same id: agent already has a hash; server returns None.
        r2 = await client.post("/auth/register", json={"agent_id": "new_pseudo"})
        assert r2.status_code == 201
        assert r2.json()["secret"] is None


@pytest.mark.asyncio
async def test_secure_rejects_missing_secret(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "me"})
        r = await client.get("/secure-whoami", headers={"X-Relay-Agent-Id": "me"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_secure_rejects_wrong_secret(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "me"})
        r = await client.get("/secure-whoami", headers={
            "X-Relay-Agent-Id": "me",
            "X-Relay-Agent-Secret": "wrong",
        })
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_secure_accepts_correct_secret(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        reg = await client.post("/auth/register", json={"agent_id": "me"})
        secret = reg.json()["secret"]
        r = await client.get("/secure-whoami", headers={
            "X-Relay-Agent-Id": "me",
            "X-Relay-Agent-Secret": secret,
        })
        assert r.status_code == 200
        assert r.json() == {"agent_id": "me"}


@pytest.mark.asyncio
async def test_secure_rejects_unknown_agent(db_session):
    app = _build_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/secure-whoami", headers={
            "X-Relay-Agent-Id": "ghost",
            "X-Relay-Agent-Secret": "anything",
        })
        assert r.status_code == 401

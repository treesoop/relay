import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.routers.auth_router import router as auth_router


def _build_app():
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(agent_id: str = Depends(require_agent_id)):
        return {"agent_id": agent_id}

    app.include_router(auth_router)
    return app


@pytest.mark.asyncio
async def test_whoami_requires_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_whoami_reads_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/whoami", headers={"X-Relay-Agent-Id": "pseudo_xyz"})
        assert r.status_code == 200
        assert r.json() == {"agent_id": "pseudo_xyz"}


@pytest.mark.asyncio
async def test_auth_register_creates_agent(db_session):
    app = _build_app()

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/auth/register", json={"agent_id": "new_pseudo"})
        assert r.status_code == 201
        assert r.json() == {"agent_id": "new_pseudo"}

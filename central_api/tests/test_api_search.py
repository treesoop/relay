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


async def _seed(client: AsyncClient, headers, *, name: str, symptom: str, approach: str, tools=()) -> str:
    r = await client.post("/skills", json={
        "name": name,
        "description": f"{name} desc",
        "when_to_use": "when",
        "body": "body",
        "metadata": {
            "problem": {"symptom": symptom},
            "solution": {"approach": approach, "tools_used": list(tools)},
            "attempts": [],
            "context": {"languages": ["python"], "libraries": []},
        },
    }, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_search_by_problem_returns_most_similar_first(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        seeder = await _register(client, "seeder")
        await _register(client, "querier")

        await _seed(client, seeder, name="a", symptom="Stripe 429 under burst",    approach="backoff")
        await _seed(client, seeder, name="b", symptom="how to center a div",        approach="flexbox")
        await _seed(client, seeder, name="c", symptom="Stripe 429 in checkout",    approach="backoff w/ header")

        headers = {"X-Relay-Agent-Id": "querier"}
        r = await client.get("/skills/search", params={
            "query": "Stripe 429 burst", "search_mode": "problem", "limit": 5,
        }, headers=headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1
        # The CSS skill should NOT be the top hit
        top_names = [it["skill"]["name"] for it in items[:2]]
        assert "b" not in top_names


@pytest.mark.asyncio
async def test_search_filters_by_available_tools(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        seeder = await _register(client, "seeder")
        await _register(client, "q")

        await _seed(client, seeder, name="needs-stripe", symptom="429", approach="retry",
                    tools=[{"type": "mcp", "name": "stripe"}])
        await _seed(client, seeder, name="self-contained", symptom="429", approach="retry", tools=[])

        # Caller has NO tools available — should only see 'self-contained'
        r = await client.get("/skills/search", params={
            "query": "429",
            "search_mode": "problem",
        }, headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        names = [it["skill"]["name"] for it in items]
        assert "needs-stripe" not in names
        assert "self-contained" in names

        # Caller has mcp:stripe available — should see both
        r = await client.get("/skills/search", params=[
            ("query", "429"),
            ("search_mode", "problem"),
            ("context_available_tools", "mcp:stripe"),
        ], headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        names = [it["skill"]["name"] for it in items]
        assert "needs-stripe" in names
        assert "self-contained" in names


@pytest.mark.asyncio
async def test_search_returns_required_and_missing_tools(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        seeder = await _register(client, "seeder")
        await _register(client, "q")

        await _seed(client, seeder, name="uses-stripe", symptom="x", approach="y",
                    tools=[{"type": "mcp", "name": "stripe"}])

        r = await client.get("/skills/search", params=[
            ("query", "x"),
            ("context_available_tools", "mcp:stripe"),
        ], headers={"X-Relay-Agent-Id": "q"})
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["required_tools"] == ["mcp:stripe"]
        assert it["missing_tools"] == []

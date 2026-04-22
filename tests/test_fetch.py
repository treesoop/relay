import httpx
import pytest

from local_mcp.fs import SkillLocation, read_skill
from local_mcp.tools.fetch import FetchInput, fetch_skill


@pytest.fixture
def fake_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/skills/sk_remote_abc" and request.method == "GET":
            return httpx.Response(200, json={
                "id": "sk_remote_abc",
                "name": "stripe-429",
                "description": "Handle 429",
                "when_to_use": "in checkout",
                "body": "## Problem\n429\n",
                "metadata": {
                    "id": "sk_remote_abc",
                    "version": 1,
                    "source_agent_id": "someone",
                    "created_at": "2026-04-21T10:00:00Z",
                    "updated_at": "2026-04-21T10:00:00Z",
                    "confidence": 0.8,
                    "used_count": 10,
                    "good_count": 8,
                    "bad_count": 0,
                    "trigger": "manual",
                    "context": {"languages": ["python"], "libraries": []},
                    "attempts": [],
                    "uploaded": True,
                    "status": "active",
                    "problem": {"symptom": "429"},
                    "solution": {"approach": "backoff", "tools_used": []},
                },
                "confidence": 0.8,
                "used_count": 10, "good_count": 8, "bad_count": 0,
                "status": "active",
                "source_agent_id": "someone",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.fetch._build_transport", lambda: transport)


@pytest.mark.asyncio
async def test_fetch_writes_to_downloaded_by_default(skill_root, fake_api):
    result = await fetch_skill(FetchInput(
        skill_id="sk_remote_abc", api_url="http://test", agent_id="me",
    ))

    assert result.location == "downloaded"
    loaded = read_skill(name="stripe-429", location=SkillLocation.DOWNLOADED)
    assert loaded.frontmatter["name"] == "stripe-429"
    assert loaded.metadata.id == "sk_remote_abc"
    assert loaded.metadata.confidence == 0.8
    assert loaded.body.strip().startswith("## Problem")


@pytest.mark.asyncio
async def test_fetch_creates_activation_symlink(skill_root, fake_api):
    await fetch_skill(FetchInput(
        skill_id="sk_remote_abc", api_url="http://test", agent_id="me",
    ))
    link = skill_root / "stripe-429"
    assert link.is_symlink()
    assert link.resolve() == (skill_root / "downloaded" / "stripe-429").resolve()
    assert (link / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_fetch_missing_id_raises(skill_root, fake_api):
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_skill(FetchInput(
            skill_id="sk_no", api_url="http://test", agent_id="me",
        ))

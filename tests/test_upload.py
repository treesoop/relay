import httpx
import pytest

from local_mcp.drift import body_hash
from local_mcp.fs import SkillLocation, read_skill, write_skill
from local_mcp.tools.upload import UploadInput, upload_skill
from local_mcp.types import Problem, RelayMetadata, Solution


@pytest.fixture
def fake_api(monkeypatch):
    """Mount an httpx MockTransport that pretends to be the central API."""
    received = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/register":
            return httpx.Response(201, json={"agent_id": "agent"})
        if request.url.path == "/skills" and request.method == "POST":
            received["body"] = request.read().decode()
            return httpx.Response(201, json={
                "id": "sk_remote_abc",
                "name": "foo",
                "description": "d",
                "when_to_use": "w",
                "body": "[REDACTED:email] body",
                "metadata": {},
                "confidence": 0.5,
                "used_count": 0, "good_count": 0, "bad_count": 0,
                "status": "active",
                "source_agent_id": "agent",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.upload._build_transport", lambda: transport)
    return received


def _write_skill_on_disk(skill_root, name: str):
    meta = RelayMetadata(
        id="sk_local",
        source_agent_id="agent",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="s"),
        solution=Solution(approach="a", tools_used=[]),
    )
    write_skill(
        name=name, location=SkillLocation.MINE,
        frontmatter={"name": name, "description": "d", "when_to_use": "w"},
        body="alice@example.com body",
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_upload_posts_skill_and_records_id(skill_root, fake_api):
    _write_skill_on_disk(skill_root, "foo")

    result = await upload_skill(UploadInput(
        name="foo", api_url="http://test", agent_id="agent",
    ))

    assert result.remote_id == "sk_remote_abc"

    # On disk the sidecar should be updated with uploaded=True and the hash.
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert loaded.metadata.uploaded is True
    assert loaded.metadata.uploaded_hash == body_hash(loaded.body)


@pytest.mark.asyncio
async def test_upload_errors_on_nonexistent_skill(skill_root, fake_api):
    with pytest.raises(FileNotFoundError):
        await upload_skill(UploadInput(
            name="does-not-exist", api_url="http://test", agent_id="agent",
        ))

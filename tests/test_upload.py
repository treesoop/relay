import httpx
import pytest

from local_mcp.credentials import load_secret, save_secret
from local_mcp.drift import body_hash
from local_mcp.fs import SkillLocation, read_skill, write_skill
from local_mcp.tools.upload import UploadInput, upload_skill
from local_mcp.types import Problem, RelayMetadata, Solution


@pytest.fixture
def fake_api(monkeypatch):
    """Mount an httpx MockTransport that pretends to be the central API."""
    received: dict = {"calls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        received["calls"].append(
            (request.method, request.url.path, dict(request.headers), request.read())
        )
        if request.url.path == "/auth/register":
            return httpx.Response(201, json={"agent_id": "agent", "secret": "s3cret-xyz"})
        if request.url.path == "/skills" and request.method == "POST":
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
        if request.url.path == "/skills/sk_remote_abc" and request.method == "PATCH":
            return httpx.Response(200, json={
                "id": "sk_remote_abc",
                "name": "foo",
                "description": "updated desc",
                "when_to_use": "w",
                "body": "[REDACTED:email] body v2",
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


def _write_skill_on_disk(skill_root, name: str, *, uploaded=False, remote_id="sk_local"):
    meta = RelayMetadata(
        id=remote_id,
        source_agent_id="agent",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="s"),
        solution=Solution(approach="a", tools_used=[]),
        uploaded=uploaded,
    )
    write_skill(
        name=name, location=SkillLocation.MINE,
        frontmatter={"name": name, "description": "d", "when_to_use": "w"},
        body="alice@example.com body",
        metadata=meta,
    )


@pytest.mark.asyncio
async def test_upload_creates_when_no_remote_id(skill_root, fake_api):
    _write_skill_on_disk(skill_root, "foo")

    result = await upload_skill(UploadInput(
        name="foo", api_url="http://test", agent_id="agent",
    ))

    assert result.remote_id == "sk_remote_abc"
    assert result.mode == "created"

    # Secret registered on first upload and persisted.
    assert load_secret("agent") == "s3cret-xyz"

    # On disk the sidecar should be updated with uploaded=True and the hash.
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert loaded.metadata.uploaded is True
    assert loaded.metadata.uploaded_hash == body_hash(loaded.body)


@pytest.mark.asyncio
async def test_upload_sends_secret_header(skill_root, fake_api):
    _write_skill_on_disk(skill_root, "foo")
    await upload_skill(UploadInput(name="foo", api_url="http://test", agent_id="agent"))
    post_call = next(
        c for c in fake_api["calls"] if c[0] == "POST" and c[1] == "/skills"
    )
    headers = post_call[2]
    assert headers["x-relay-agent-id"] == "agent"
    assert headers["x-relay-agent-secret"] == "s3cret-xyz"


@pytest.mark.asyncio
async def test_upload_uses_existing_secret_without_reregister(skill_root, fake_api):
    save_secret("agent", "already-saved")
    _write_skill_on_disk(skill_root, "foo")

    await upload_skill(UploadInput(name="foo", api_url="http://test", agent_id="agent"))

    # Should NOT have called /auth/register because we already had a local secret.
    assert not any(c[1] == "/auth/register" for c in fake_api["calls"])
    post_call = next(
        c for c in fake_api["calls"] if c[0] == "POST" and c[1] == "/skills"
    )
    assert post_call[2]["x-relay-agent-secret"] == "already-saved"


@pytest.mark.asyncio
async def test_upload_patches_when_already_uploaded(skill_root, fake_api):
    save_secret("agent", "already-saved")
    _write_skill_on_disk(skill_root, "foo", uploaded=True, remote_id="sk_remote_abc")

    result = await upload_skill(UploadInput(
        name="foo", api_url="http://test", agent_id="agent",
    ))

    assert result.mode == "updated"
    assert result.remote_id == "sk_remote_abc"
    # Confirm a PATCH was actually issued to the canonical id.
    patch_calls = [c for c in fake_api["calls"] if c[0] == "PATCH"]
    assert len(patch_calls) == 1
    assert patch_calls[0][1] == "/skills/sk_remote_abc"


@pytest.mark.asyncio
async def test_upload_errors_on_nonexistent_skill(skill_root, fake_api):
    with pytest.raises(FileNotFoundError):
        await upload_skill(UploadInput(
            name="does-not-exist", api_url="http://test", agent_id="agent",
        ))

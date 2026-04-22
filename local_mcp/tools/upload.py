from __future__ import annotations

from dataclasses import dataclass

import httpx

from local_mcp.credentials import load_secret, save_secret
from local_mcp.drift import body_hash
from local_mcp.fs import SkillLocation, read_skill, write_skill


@dataclass
class UploadInput:
    name: str
    api_url: str
    agent_id: str


@dataclass
class UploadResult:
    remote_id: str
    api_url: str
    mode: str  # "created" or "updated"


def _build_transport() -> httpx.BaseTransport | None:
    """Test hook: returns None to use the real network; overridden in tests."""
    return None


async def _ensure_agent_secret(client: httpx.AsyncClient, agent_id: str) -> str:
    """Return the secret for agent_id, registering with the server if we don't have one locally.

    If the server responds with `secret=null`, the agent is already registered on the server
    but we've lost the local copy — there's no recovery path without an admin reset, so we
    raise loudly.
    """
    existing = load_secret(agent_id)
    if existing:
        return existing

    resp = await client.post("/auth/register", json={"agent_id": agent_id})
    if resp.status_code not in (200, 201, 409):
        resp.raise_for_status()
    data = resp.json()
    secret = data.get("secret")
    if not secret:
        raise RuntimeError(
            f"Agent {agent_id} is registered on the server but no local secret is available. "
            "Either recover the original credentials.json or re-register with a new agent_id."
        )
    save_secret(agent_id, secret)
    return secret


async def upload_skill(inp: UploadInput) -> UploadResult:
    loaded = read_skill(name=inp.name, location=SkillLocation.MINE)

    payload = {
        "name": inp.name,
        "description": loaded.frontmatter.get("description", ""),
        "when_to_use": loaded.frontmatter.get("when_to_use"),
        "body": loaded.body,
        "metadata": loaded.metadata.to_dict(),
        "source_agent_id": inp.agent_id,
    }

    existing_id = loaded.metadata.id if (loaded.metadata.uploaded and loaded.metadata.id) else None

    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        secret = await _ensure_agent_secret(client, inp.agent_id)
        client.headers["X-Relay-Agent-Secret"] = secret

        if existing_id:
            # Overwrite: server checks source_agent_id == auth agent and rejects otherwise.
            resp = await client.patch(f"/skills/{existing_id}", json={
                "name": payload["name"],
                "description": payload["description"],
                "when_to_use": payload["when_to_use"],
                "body": payload["body"],
                "metadata": payload["metadata"],
            })
            resp.raise_for_status()
            data = resp.json()
            mode = "updated"
        else:
            resp = await client.post("/skills", json=payload)
            resp.raise_for_status()
            data = resp.json()
            mode = "created"

    # The server may have masked PII in body and/or attempts. We read back from the server
    # and rewrite local files so they mirror the commons version.
    loaded.metadata.uploaded = True
    loaded.metadata.uploaded_hash = body_hash(data["body"])
    loaded.metadata.id = data["id"]
    # Persist masked body locally too so drift doesn't fire on first read.
    write_skill(
        name=inp.name,
        location=SkillLocation.MINE,
        frontmatter=dict(loaded.frontmatter),
        body=data["body"],
        metadata=loaded.metadata,
    )

    return UploadResult(remote_id=data["id"], api_url=inp.api_url, mode=mode)

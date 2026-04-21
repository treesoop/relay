from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from local_mcp.fs import SkillLocation, write_skill
from local_mcp.types import RelayMetadata


FetchMode = Literal["downloaded", "staging"]


@dataclass
class FetchInput:
    skill_id: str
    api_url: str
    agent_id: str
    mode: FetchMode = "downloaded"


@dataclass
class FetchResult:
    name: str
    location: str
    skill_id: str


def _build_transport() -> httpx.BaseTransport | None:
    """Test hook: returns None to use the real network; overridden in tests."""
    return None


async def fetch_skill(inp: FetchInput) -> FetchResult:
    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        resp = await client.get(f"/skills/{inp.skill_id}")
        resp.raise_for_status()
        data = resp.json()

    name = data["name"]
    frontmatter = {
        "name": name,
        "description": data["description"],
        "when_to_use": data.get("when_to_use"),
    }
    # Strip frontmatter values that are None to keep the YAML clean.
    frontmatter = {k: v for k, v in frontmatter.items() if v is not None}

    metadata = RelayMetadata.from_dict(data["metadata"])
    # Server is the source of truth on counts/confidence when fetched.
    metadata.confidence = data["confidence"]
    metadata.used_count = data["used_count"]
    metadata.good_count = data["good_count"]
    metadata.bad_count = data["bad_count"]
    metadata.status = data["status"]

    location = (
        SkillLocation.STAGING if inp.mode == "staging" else SkillLocation.DOWNLOADED
    )
    write_skill(
        name=name,
        location=location,
        frontmatter=frontmatter,
        body=data["body"],
        metadata=metadata,
    )
    return FetchResult(name=name, location=location.value, skill_id=data["id"])

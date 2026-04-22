from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from local_mcp.credentials import load_secret


Signal = Literal["good", "bad", "stale"]


@dataclass
class ReviewInput:
    skill_id: str
    api_url: str
    agent_id: str
    signal: Signal
    reason: str | None = None
    note: str | None = None


@dataclass
class ReviewResult:
    review_id: int
    skill_id: str


def _build_transport() -> httpx.BaseTransport | None:
    return None


async def review_skill(inp: ReviewInput) -> ReviewResult:
    payload: dict[str, str | None] = {"signal": inp.signal}
    if inp.reason is not None:
        payload["reason"] = inp.reason
    if inp.note is not None:
        payload["note"] = inp.note

    headers = {"X-Relay-Agent-Id": inp.agent_id}
    secret = load_secret(inp.agent_id)
    if secret is None:
        raise RuntimeError(
            f"No local secret for agent {inp.agent_id}. Run an upload first or re-register."
        )
    headers["X-Relay-Agent-Secret"] = secret

    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers=headers,
        transport=transport,
        timeout=30.0,
    ) as client:
        resp = await client.post(f"/skills/{inp.skill_id}/reviews", json=payload)
        resp.raise_for_status()
        data = resp.json()

    return ReviewResult(review_id=data["id"], skill_id=data["skill_id"])

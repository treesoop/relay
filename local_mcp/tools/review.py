from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


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

    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        resp = await client.post(f"/skills/{inp.skill_id}/reviews", json=payload)
        resp.raise_for_status()
        data = resp.json()

    return ReviewResult(review_id=data["id"], skill_id=data["skill_id"])

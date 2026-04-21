from __future__ import annotations

from fastapi import Header, HTTPException, status


async def require_agent_id(
    x_relay_agent_id: str | None = Header(default=None, alias="X-Relay-Agent-Id"),
) -> str:
    if not x_relay_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Relay-Agent-Id header",
        )
    return x_relay_agent_id

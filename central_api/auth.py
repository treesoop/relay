from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.db import get_session
from central_api.models import Agent


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


async def require_agent_id(
    x_relay_agent_id: str | None = Header(default=None, alias="X-Relay-Agent-Id"),
) -> str:
    """Loose auth: header must be present. Used for read-only telemetry endpoints."""
    if not x_relay_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Relay-Agent-Id header",
        )
    return x_relay_agent_id


async def require_authenticated_agent(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_relay_agent_id: str | None = Header(default=None, alias="X-Relay-Agent-Id"),
    x_relay_agent_secret: str | None = Header(default=None, alias="X-Relay-Agent-Secret"),
) -> str:
    """Strict auth: header + secret verified against agents.secret_hash. Used for write endpoints."""
    if not x_relay_agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Relay-Agent-Id header",
        )
    if not x_relay_agent_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Relay-Agent-Secret header",
        )
    agent = await session.get(Agent, x_relay_agent_id)
    if agent is None or agent.secret_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent is not registered. Call POST /auth/register to obtain a secret.",
        )
    if hash_secret(x_relay_agent_secret) != agent.secret_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent secret",
        )
    return x_relay_agent_id

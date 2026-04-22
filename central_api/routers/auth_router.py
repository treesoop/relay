from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import hash_secret
from central_api.db import get_session
from central_api.models import Agent


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    agent_id: str


class RegisterResponse(BaseModel):
    agent_id: str
    # Returned only when a secret is freshly issued. Clients must persist it; the server only stores its hash.
    secret: str | None = None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RegisterResponse:
    agent = await session.get(Agent, body.agent_id)

    if agent is not None and agent.secret_hash is not None:
        # Agent already has a secret. We never hand it out again.
        return RegisterResponse(agent_id=body.agent_id, secret=None)

    new_secret = secrets.token_urlsafe(32)
    if agent is None:
        agent = Agent(id=body.agent_id, secret_hash=hash_secret(new_secret))
        session.add(agent)
    else:
        agent.secret_hash = hash_secret(new_secret)

    await session.commit()
    return RegisterResponse(agent_id=body.agent_id, secret=new_secret)

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.db import get_session
from central_api.models import Agent


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    agent_id: str


class RegisterResponse(BaseModel):
    agent_id: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    stmt = insert(Agent).values(id=body.agent_id).on_conflict_do_nothing(index_elements=["id"])
    await session.execute(stmt)
    await session.commit()
    return RegisterResponse(agent_id=body.agent_id)

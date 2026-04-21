from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.models import Review, Skill
from central_api.schemas import ReviewRequest, ReviewResponse


router = APIRouter(prefix="/skills", tags=["reviews"])


@router.post(
    "/{skill_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_review(
    skill_id: str,
    body: ReviewRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent_id: Annotated[str, Depends(require_agent_id)],
) -> ReviewResponse:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")

    review = Review(
        skill_id=skill_id,
        agent_id=agent_id,
        signal=body.signal,
        reason=body.reason,
        note=body.note,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    return ReviewResponse(
        id=review.id,
        skill_id=review.skill_id,
        agent_id=review.agent_id,
        signal=review.signal,  # type: ignore[arg-type]
        reason=review.reason,
        note=review.note,
    )

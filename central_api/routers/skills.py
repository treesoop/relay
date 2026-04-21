from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.embedding import EmbeddingClient, build_embedding_targets
from central_api.masking import mask_pii
from central_api.models import Skill
from central_api.schemas import SkillResponse, SkillUploadRequest


router = APIRouter(prefix="/skills", tags=["skills"])


def _new_id() -> str:
    return f"sk_{secrets.token_hex(8)}"


def _to_response(s: Skill) -> SkillResponse:
    return SkillResponse(
        id=s.id, name=s.name, description=s.description, when_to_use=s.when_to_use,
        body=s.body, metadata=s.metadata_, confidence=s.confidence,
        used_count=s.used_count, good_count=s.good_count, bad_count=s.bad_count,
        status=s.status, source_agent_id=s.source_agent_id,
    )


def _mask_metadata(meta: dict) -> dict:
    """Mask PII inside nested strings of attempts[].failed_because."""
    out = dict(meta)
    attempts = [dict(a) for a in (meta.get("attempts") or [])]
    for a in attempts:
        if "failed_because" in a and isinstance(a["failed_because"], str):
            a["failed_because"] = mask_pii(a["failed_because"])
    out["attempts"] = attempts
    return out


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    body: SkillUploadRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent_id: Annotated[str, Depends(require_agent_id)],
) -> SkillResponse:
    embedder: EmbeddingClient = request.app.state.embedder

    masked_body = mask_pii(body.body)
    masked_meta = _mask_metadata(body.metadata)

    targets = build_embedding_targets(description=body.description, metadata=masked_meta)
    desc_vec, problem_vec, solution_vec = await embedder.embed_many(
        [targets["description"], targets["problem"], targets["solution"]]
    )

    skill = Skill(
        id=_new_id(),
        name=body.name,
        description=body.description,
        when_to_use=body.when_to_use,
        body=masked_body,
        metadata_=masked_meta,
        description_embedding=desc_vec,
        problem_embedding=problem_vec,
        solution_embedding=solution_vec,
        source_agent_id=body.source_agent_id or agent_id,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return _to_response(skill)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[str, Depends(require_agent_id)],
) -> SkillResponse:
    s = await session.get(Skill, skill_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    return _to_response(s)

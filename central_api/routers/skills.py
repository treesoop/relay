from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.embedding import EmbeddingClient, build_embedding_targets
from central_api.masking import mask_pii
from central_api.models import Skill
from central_api.ranking import combine_score, context_match_score
from central_api.schemas import (
    SearchMode,
    SearchResponse,
    SearchResultItem,
    SkillResponse,
    SkillUploadRequest,
)


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


def _required_tools(metadata: dict) -> list[str]:
    tools_used = (metadata.get("solution") or {}).get("tools_used") or []
    return [f"{t['type']}:{t['name']}" for t in tools_used if t.get("type") == "mcp"]


_EMB_COLUMN_BY_MODE = {
    "description": Skill.description_embedding,
    "problem": Skill.problem_embedding,
    "solution": Skill.solution_embedding,
}


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


@router.get("/search", response_model=SearchResponse)
async def search(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Annotated[str, Depends(require_agent_id)],
    request: Request,
    query: str = Query(...),
    search_mode: SearchMode = Query("problem"),
    limit: int = Query(5, ge=1, le=50),
    context_languages: list[str] = Query(default_factory=list),
    context_libraries: list[str] = Query(default_factory=list),
    context_available_tools: list[str] = Query(default_factory=list),
) -> SearchResponse:
    embedder: EmbeddingClient = request.app.state.embedder
    query_vec = await embedder.embed(query)

    if search_mode == "hybrid":
        col_d = Skill.description_embedding
        col_p = Skill.problem_embedding
        col_s = Skill.solution_embedding
        distance_expr = (
            col_d.cosine_distance(query_vec)
            + col_p.cosine_distance(query_vec)
            + col_s.cosine_distance(query_vec)
        ) / 3.0
    else:
        col = _EMB_COLUMN_BY_MODE[search_mode]
        distance_expr = col.cosine_distance(query_vec)

    stmt = (
        select(Skill, distance_expr.label("distance"))
        .where(Skill.status == "active")
        .order_by(distance_expr)
        .limit(limit * 4)  # overfetch — we filter by tools then trim to `limit`
    )
    rows = (await session.execute(stmt)).all()

    available = set(context_available_tools)
    items: list[SearchResultItem] = []
    for skill, distance in rows:
        required = _required_tools(skill.metadata_)
        missing = [t for t in required if t not in available]
        if required and missing:
            continue

        similarity = max(0.0, 1.0 - float(distance))
        ctx_match = context_match_score(
            skill_context=(skill.metadata_.get("context") or {}),
            query_languages=context_languages,
            query_libraries=context_libraries,
        )

        items.append(SearchResultItem(
            skill=_to_response(skill),
            similarity=similarity,
            confidence=skill.confidence,
            context_match=ctx_match,
            matched_on=search_mode,
            required_tools=required,
            missing_tools=missing,
        ))

        if len(items) >= limit:
            break

    items.sort(
        key=lambda it: combine_score(
            similarity=it.similarity,
            confidence=it.confidence,
            context_match=it.context_match,
        ),
        reverse=True,
    )

    return SearchResponse(items=items)


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

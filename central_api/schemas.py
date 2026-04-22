from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SearchMode = Literal["problem", "solution", "description", "hybrid"]


# Server-side size caps. Client can send arbitrary strings; Pydantic rejects oversize input at 422.
NAME_MAX = 200
DESCRIPTION_MAX = 2000
WHEN_TO_USE_MAX = 1000
BODY_MAX = 50_000


class SkillUploadRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=NAME_MAX)
    description: str = Field(..., min_length=1, max_length=DESCRIPTION_MAX)
    when_to_use: str | None = Field(default=None, max_length=WHEN_TO_USE_MAX)
    body: str = Field(..., min_length=1, max_length=BODY_MAX)
    metadata: dict[str, Any]
    # Optional: server can default source_agent_id from the header; request override allowed for CLI tests.
    source_agent_id: str | None = None


class SkillUpdateRequest(BaseModel):
    """Partial update. Unset fields leave the stored value untouched."""
    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    description: str | None = Field(default=None, min_length=1, max_length=DESCRIPTION_MAX)
    when_to_use: str | None = Field(default=None, max_length=WHEN_TO_USE_MAX)
    body: str | None = Field(default=None, min_length=1, max_length=BODY_MAX)
    metadata: dict[str, Any] | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    when_to_use: str | None
    body: str
    metadata: dict[str, Any]
    confidence: float
    used_count: int
    good_count: int
    bad_count: int
    status: str
    source_agent_id: str


class SearchRequest(BaseModel):
    query: str
    search_mode: SearchMode = "problem"
    limit: int = Field(default=5, ge=1, le=50)
    context_languages: list[str] = Field(default_factory=list)
    context_libraries: list[str] = Field(default_factory=list)
    context_available_tools: list[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    skill: SkillResponse
    similarity: float
    confidence: float
    context_match: float
    matched_on: SearchMode
    required_tools: list[str]
    missing_tools: list[str]


class SearchResponse(BaseModel):
    items: list[SearchResultItem]


ReviewSignal = Literal["good", "bad", "stale"]


class ReviewRequest(BaseModel):
    signal: ReviewSignal
    reason: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    id: int
    skill_id: str
    agent_id: str
    signal: ReviewSignal
    reason: str | None
    note: str | None

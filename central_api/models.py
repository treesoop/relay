from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    secret_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # "metadata" is reserved on Base, so suffix with underscore and map to the real column.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)

    description_embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    problem_embedding:     Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    solution_embedding:    Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    used_count: Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    good_count: Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    bad_count:  Mapped[int]   = mapped_column(Integer, default=0, server_default="0")
    status:     Mapped[str]   = mapped_column(String, default="active", server_default="active")

    source_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("signal IN ('good', 'bad', 'stale')", name="reviews_signal_check"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    signal:   Mapped[str] = mapped_column(String, nullable=False)
    reason:   Mapped[str | None] = mapped_column(String, nullable=True)
    note:     Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageLog(Base):
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False)
    query:    Mapped[str | None]   = mapped_column(Text, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    used:     Mapped[int]  = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

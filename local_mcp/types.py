from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

import yaml


ToolType = Literal["mcp", "library", "cli"]
_VALID_TOOL_TYPES: set[str] = {"mcp", "library", "cli"}


@dataclass
class Attempt:
    tried: str | None = None
    failed_because: str | None = None
    worked: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attempt:
        return cls(
            tried=d.get("tried"),
            failed_because=d.get("failed_because"),
            worked=d.get("worked"),
        )


@dataclass
class ToolUsed:
    type: ToolType
    name: str

    def __post_init__(self) -> None:
        if self.type not in _VALID_TOOL_TYPES:
            raise ValueError(
                f"ToolUsed.type must be one of {sorted(_VALID_TOOL_TYPES)}, got {self.type!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolUsed:
        return cls(type=d["type"], name=d["name"])


@dataclass
class Problem:
    symptom: str
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"symptom": self.symptom}
        if self.context is not None:
            d["context"] = self.context
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Problem:
        return cls(symptom=d["symptom"], context=d.get("context"))


@dataclass
class Solution:
    approach: str
    tools_used: list[ToolUsed] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approach": self.approach,
            "tools_used": [t.to_dict() for t in self.tools_used],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Solution:
        return cls(
            approach=d["approach"],
            tools_used=[ToolUsed.from_dict(t) for t in d.get("tools_used", [])],
        )


@dataclass
class RelayMetadata:
    # Numeric invariants (counts, confidence bounds) are owned by the central server.
    # Local files mirror server state — we do not re-validate them here.
    id: str
    source_agent_id: str
    created_at: str
    updated_at: str

    version: int = 1

    confidence: float = 0.5
    used_count: int = 0
    good_count: int = 0
    bad_count: int = 0

    trigger: str = "manual"
    context: dict[str, Any] = field(default_factory=dict)

    problem: Problem | None = None
    solution: Solution | None = None
    attempts: list[Attempt] = field(default_factory=list)

    uploaded: bool = False
    uploaded_hash: str | None = None

    status: str = "active"
    last_verified: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "version": self.version,
            "source_agent_id": self.source_agent_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confidence": self.confidence,
            "used_count": self.used_count,
            "good_count": self.good_count,
            "bad_count": self.bad_count,
            "trigger": self.trigger,
            "context": self.context,
            "attempts": [a.to_dict() for a in self.attempts],
            "uploaded": self.uploaded,
            "status": self.status,
        }
        if self.problem is not None:
            d["problem"] = self.problem.to_dict()
        if self.solution is not None:
            d["solution"] = self.solution.to_dict()
        if self.uploaded_hash is not None:
            d["uploaded_hash"] = self.uploaded_hash
        if self.last_verified is not None:
            d["last_verified"] = self.last_verified
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RelayMetadata:
        return cls(
            id=d["id"],
            source_agent_id=d["source_agent_id"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            version=d.get("version", 1),
            confidence=d.get("confidence", 0.5),
            used_count=d.get("used_count", 0),
            good_count=d.get("good_count", 0),
            bad_count=d.get("bad_count", 0),
            trigger=d.get("trigger", "manual"),
            context=d.get("context", {}),
            problem=Problem.from_dict(d["problem"]) if d.get("problem") else None,
            solution=Solution.from_dict(d["solution"]) if d.get("solution") else None,
            attempts=[Attempt.from_dict(a) for a in d.get("attempts", [])],
            uploaded=d.get("uploaded", False),
            uploaded_hash=d.get("uploaded_hash"),
            status=d.get("status", "active"),
            last_verified=d.get("last_verified"),
        )

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, text: str) -> RelayMetadata:
        return cls.from_dict(yaml.safe_load(text))

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from local_mcp.fs import SkillFiles, SkillLocation, write_skill
from local_mcp.types import Attempt, Problem, RelayMetadata, Solution, ToolUsed


@dataclass
class CaptureInput:
    name: str
    description: str
    when_to_use: str

    problem_symptom: str
    problem_context: str | None
    solution_approach: str

    attempts: list[dict[str, Any]]
    tools_used: list[dict[str, Any]]

    languages: list[str]
    libraries: list[str]
    domain: str | None

    body_sections: dict[str, str]
    source_agent_id: str

    trigger: str = "manual"


@dataclass
class CaptureResult:
    name: str
    location: str
    files: SkillFiles
    id: str


_BODY_ORDER = ["Problem", "What I tried", "What worked", "Tools used", "When NOT to use this"]


def _render_body(sections: dict[str, str]) -> str:
    ordered = [h for h in _BODY_ORDER if h in sections]
    extras = [h for h in sections if h not in _BODY_ORDER]
    chunks = []
    for heading in ordered + extras:
        chunks.append(f"## {heading}\n\n{sections[heading].rstrip()}\n")
    return "\n".join(chunks).rstrip() + "\n"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return f"sk_{secrets.token_hex(8)}"


def capture_skill(inp: CaptureInput) -> CaptureResult:
    now = _now_iso()
    skill_id = _new_id()

    attempts = [Attempt.from_dict(a) for a in inp.attempts]
    tools = [ToolUsed.from_dict(t) for t in inp.tools_used]

    metadata = RelayMetadata(
        id=skill_id,
        source_agent_id=inp.source_agent_id,
        created_at=now,
        updated_at=now,
        trigger=inp.trigger,
        context={
            "languages": inp.languages,
            "libraries": inp.libraries,
            **({"domain": inp.domain} if inp.domain else {}),
        },
        problem=Problem(symptom=inp.problem_symptom, context=inp.problem_context),
        solution=Solution(approach=inp.solution_approach, tools_used=tools),
        attempts=attempts,
    )

    frontmatter: dict[str, Any] = {
        "name": inp.name,
        "description": inp.description,
        "when_to_use": inp.when_to_use,
    }

    body = _render_body(inp.body_sections)

    files = write_skill(
        name=inp.name,
        location=SkillLocation.MINE,
        frontmatter=frontmatter,
        body=body,
        metadata=metadata,
    )

    return CaptureResult(
        name=inp.name,
        location=SkillLocation.MINE.value,
        files=files,
        id=skill_id,
    )

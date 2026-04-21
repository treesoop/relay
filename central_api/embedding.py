from __future__ import annotations

import hashlib
from typing import Any, Protocol

from openai import AsyncOpenAI

from central_api.config import get_settings


def build_embedding_targets(
    *,
    description: str,
    metadata: dict[str, Any],
) -> dict[str, str]:
    """Build the three text blobs we embed per skill.

    Returns a dict with keys 'description', 'problem', 'solution'.
    """
    problem = metadata.get("problem") or {}
    solution = metadata.get("solution") or {}
    attempts = metadata.get("attempts") or []

    problem_text = " ".join(
        t for t in [problem.get("symptom"), problem.get("context")] if t
    )

    attempts_summary = "; ".join(
        (a.get("tried") or a.get("worked") or "") + (
            f" (failed: {a['failed_because']})" if a.get("failed_because") else ""
        )
        for a in attempts
    ).strip()

    tools_used = solution.get("tools_used") or []
    tool_names = ", ".join(t.get("name", "") for t in tools_used)

    solution_text = " ".join(
        t for t in [
            solution.get("approach"),
            f"tools: {tool_names}" if tool_names else "",
            f"attempts: {attempts_summary}" if attempts_summary else "",
        ] if t
    )

    return {
        "description": description,
        "problem": problem_text,
        "solution": solution_text,
    }


class EmbeddingClient(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.embedding_model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(input=[text], model=self._model)
        return list(resp.data[0].embedding)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(input=texts, model=self._model)
        return [list(d.embedding) for d in resp.data]


class StubEmbedder:
    """Deterministic fake embedder for tests. sha256(text) hashed down to floats."""

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # Tile the digest bytes to fill dim dimensions; normalize to [-1, 1].
        out: list[float] = []
        i = 0
        while len(out) < self._dim:
            b = seed[i % len(seed)]
            out.append((b / 255.0) * 2 - 1)
            i += 1
        return out

    async def embed(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

from __future__ import annotations

from typing import Any


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def context_match_score(
    *,
    skill_context: dict[str, Any],
    query_languages: list[str],
    query_libraries: list[str],
) -> float:
    """Return a [0, 1] score for how well a skill's context matches the query's.

    With empty query-side context, returns 1.0 (we don't penalize for missing info).
    Otherwise averages the Jaccard overlap for languages and libraries.
    """
    if not query_languages and not query_libraries:
        return 1.0

    scores: list[float] = []
    if query_languages:
        scores.append(
            _jaccard(set(skill_context.get("languages") or []), set(query_languages))
        )
    if query_libraries:
        scores.append(
            _jaccard(set(skill_context.get("libraries") or []), set(query_libraries))
        )
    return sum(scores) / len(scores)


def combine_score(*, similarity: float, confidence: float, context_match: float) -> float:
    """Hybrid ranking: 0.5 similarity + 0.3 confidence + 0.2 context_match."""
    return 0.5 * similarity + 0.3 * confidence + 0.2 * context_match

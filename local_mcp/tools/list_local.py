from __future__ import annotations

from typing import Any

from local_mcp.config import get_skill_root
from local_mcp.drift import check_drift
from local_mcp.fs import RELAY_YAML, SKILL_MD, SkillLocation, read_skill


def list_local_skills() -> list[dict[str, Any]]:
    root = get_skill_root()
    results: list[dict[str, Any]] = []

    for location in SkillLocation:
        base = root / location.value
        if not base.exists():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir():
                continue
            if not (entry / SKILL_MD).exists() or not (entry / RELAY_YAML).exists():
                continue
            try:
                loaded = read_skill(name=entry.name, location=location)
            except Exception:
                continue

            results.append({
                "id": loaded.metadata.id,
                "name": entry.name,
                "location": location.value,
                "symptom": loaded.metadata.problem.symptom if loaded.metadata.problem else None,
                "confidence": loaded.metadata.confidence,
                "uploaded": loaded.metadata.uploaded,
                "drift_detected": check_drift(loaded),
            })

    return results

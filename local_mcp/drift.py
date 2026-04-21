from __future__ import annotations

import hashlib

from local_mcp.fs import LoadedSkill


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_drift(loaded: LoadedSkill) -> bool:
    """True if the skill was uploaded and the current body differs from uploaded_hash."""
    if not loaded.metadata.uploaded:
        return False
    if loaded.metadata.uploaded_hash is None:
        return False
    return body_hash(loaded.body) != loaded.metadata.uploaded_hash

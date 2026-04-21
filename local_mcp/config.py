from __future__ import annotations

import os
from pathlib import Path


def get_skill_root() -> Path:
    """Root directory for Relay-managed skills.

    Precedence: RELAY_SKILL_ROOT env var > ~/.claude/skills default.
    """
    env = os.environ.get("RELAY_SKILL_ROOT")
    if env:
        return Path(env)
    return Path(os.environ["HOME"]) / ".claude" / "skills"

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from local_mcp.config import get_skill_root


class SkillLocation(str, Enum):
    MINE = "mine"
    DOWNLOADED = "downloaded"
    STAGING = "staging"


# kebab-case-ish, 1-80 chars, no path separators, no dots at edges
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def _validate_name(name: str) -> None:
    if not name or not _NAME_RE.match(name):
        raise ValueError(f"invalid skill name: {name!r}")


def skill_dir(name: str, location: SkillLocation) -> Path:
    _validate_name(name)
    return get_skill_root() / location.value / name

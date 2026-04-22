from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import frontmatter as fm_lib
import yaml

from local_mcp.config import get_skill_root
from local_mcp.types import RelayMetadata


class SkillLocation(str, Enum):
    MINE = "mine"
    DOWNLOADED = "downloaded"


# kebab-case-ish, 1-80 chars, no path separators, no dots at edges
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def _validate_name(name: str) -> None:
    if not name or not _NAME_RE.match(name):
        raise ValueError(f"invalid skill name: {name!r}")


def skill_dir(name: str, location: SkillLocation) -> Path:
    _validate_name(name)
    return get_skill_root() / location.value / name


SKILL_MD = "SKILL.md"
RELAY_YAML = ".relay.yaml"


@dataclass
class SkillFiles:
    dir: Path
    skill_md: Path
    relay_yaml: Path


@dataclass
class LoadedSkill:
    frontmatter: dict[str, Any]
    body: str
    metadata: RelayMetadata
    files: SkillFiles


def _files_for(name: str, location: SkillLocation) -> SkillFiles:
    d = skill_dir(name, location)
    return SkillFiles(dir=d, skill_md=d / SKILL_MD, relay_yaml=d / RELAY_YAML)


def _activate_symlink(name: str, target: Path) -> None:
    """Create ~/.claude/skills/<name> symlink pointing at the real skill dir.

    Claude Code auto-activates skills found at `~/.claude/skills/<name>/SKILL.md`.
    Our real storage nests under mine/ or downloaded/, so the symlink flattens
    the layout without losing the mine-vs-downloaded semantic.

    Idempotent: replaces any existing link/dir at that path.
    """
    link = get_skill_root() / name
    # Clean up anything already there — symlink, broken symlink, or accidental dir.
    if link.is_symlink() or link.exists():
        try:
            link.unlink()
        except IsADirectoryError:
            # Only happens if someone manually mkdir'd at the flat path; refuse to touch.
            return
    link.symlink_to(target, target_is_directory=True)


def write_skill(
    *,
    name: str,
    location: SkillLocation,
    frontmatter: dict[str, Any],
    body: str,
    metadata: RelayMetadata,
) -> SkillFiles:
    files = _files_for(name, location)
    files.dir.mkdir(parents=True, exist_ok=True)

    post = fm_lib.Post(body, **frontmatter)
    files.skill_md.write_text(fm_lib.dumps(post) + "\n", encoding="utf-8")
    files.relay_yaml.write_text(metadata.to_yaml(), encoding="utf-8")

    # Flatten into the Claude-Code-scanned layout so auto-activation fires.
    _activate_symlink(name, files.dir)

    return files


def read_skill(*, name: str, location: SkillLocation) -> LoadedSkill:
    files = _files_for(name, location)
    if not files.skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found: {files.skill_md}")
    if not files.relay_yaml.exists():
        raise FileNotFoundError(f".relay.yaml not found: {files.relay_yaml}")

    post = fm_lib.loads(files.skill_md.read_text(encoding="utf-8"))
    metadata = RelayMetadata.from_yaml(files.relay_yaml.read_text(encoding="utf-8"))
    return LoadedSkill(
        frontmatter=dict(post.metadata),
        body=post.content,
        metadata=metadata,
        files=files,
    )

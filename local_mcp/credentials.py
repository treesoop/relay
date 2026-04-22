"""Store the per-agent secret so writes can be authenticated against the central API.

The secret is issued exactly once by POST /auth/register and then persisted to
~/.config/relay/credentials.json (0600). It's never transmitted again except as
the X-Relay-Agent-Secret header on write requests.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _config_path() -> Path:
    override = os.environ.get("RELAY_CREDENTIALS_PATH")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path(os.environ["HOME"]) / ".config"))
    return base / "relay" / "credentials.json"


@dataclass
class Credentials:
    agent_id: str
    secret: str


def load_secret(agent_id: str) -> str | None:
    """Return the stored secret for agent_id, or None if not present."""
    path = _config_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    agents = data.get("agents", {})
    entry = agents.get(agent_id)
    if not entry:
        return None
    return entry.get("secret")


def save_secret(agent_id: str, secret: str) -> Path:
    """Persist agent_id → secret under 0600 permissions. Returns the file path."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data.setdefault("agents", {})[agent_id] = {"secret": secret}

    # Write via a temp sibling to avoid half-written files; then chmod tight.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path

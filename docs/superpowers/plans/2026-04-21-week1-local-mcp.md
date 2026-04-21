# Relay Week 1 — Local MCP + File Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local MCP server that lets an agent capture a problem-solving session into a Claude Code skill (`SKILL.md` + `.relay.yaml` sidecar), and list all locally stored skills with drift detection. No central server yet.

**Architecture:** File-system as storage (no local DB). Skills live under `~/.claude/skills/{mine,downloaded,staging}/<name>/` as a directory containing `SKILL.md` (Claude Code official format) and `.relay.yaml` (Relay-specific metadata). Six MCP tools exposed via FastMCP stdio; Week 1 implements 2 of them (`skill_capture`, `skill_list_local`). Claude Code plugin manifest registers the MCP server and provides a slash command for manual capture.

**Tech Stack:**
- Python 3.11+, FastMCP (stdio MCP server)
- PyYAML (sidecar), python-frontmatter (SKILL.md parsing)
- pytest + pytest-asyncio (TDD)
- Claude Code plugin spec (`.claude-plugin/plugin.json`)

---

## File Structure

```
relay/
├── SPEC.md                                  # already exists
├── pyproject.toml                           # new
├── .gitignore                               # new
├── README.md                                # new (minimal)
│
├── local_mcp/
│   ├── __init__.py                          # empty marker
│   ├── types.py                             # dataclasses for Skill / RelayMetadata
│   ├── config.py                            # paths, env vars
│   ├── fs.py                                # directory conventions + file I/O
│   ├── drift.py                             # body-hash drift detection
│   ├── server.py                            # FastMCP entry point
│   └── tools/
│       ├── __init__.py                      # empty marker
│       ├── capture.py                       # skill_capture tool
│       └── list_local.py                    # skill_list_local tool
│
├── adapters/
│   └── claude/
│       ├── .claude-plugin/
│       │   └── plugin.json                  # Claude Code plugin manifest
│       ├── SKILL.md                         # agent behavior guidance
│       └── commands/
│           └── relay-capture.md             # /relay:capture slash command
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                          # tmp_path fixtures for skill root
│   ├── test_types.py
│   ├── test_fs.py
│   ├── test_drift.py
│   ├── test_capture.py
│   └── test_list_local.py
│
└── docs/
    ├── superpowers/plans/
    │   └── 2026-04-21-week1-local-mcp.md    # this file
    └── verification/
        └── day0-claude-code-skills.md       # empirical verification results
```

**Responsibilities:**
- `types.py` — typed domain model (`Problem`, `Solution`, `Attempt`, `ToolUsed`, `RelayMetadata`). Parseable from / serializable to YAML.
- `fs.py` — knows directory conventions, writes/reads `SKILL.md` + `.relay.yaml` pairs, computes slug/paths.
- `drift.py` — computes body hash, compares with `uploaded_hash`.
- `tools/*.py` — MCP tool handlers. Thin; delegate to `fs.py` + `drift.py`.
- `server.py` — FastMCP instance, registers tools.
- `adapters/claude/` — user-facing integration layer.

---

## Task 0: Day-0 Empirical Verification of Claude Code Skills

**Goal:** Before committing to the directory+sidecar design, verify Claude Code actually handles our intended layout. Document results in `docs/verification/day0-claude-code-skills.md`.

This is investigation, not code. Required output: a verification report with pass/fail on 4 checks.

**Files:**
- Create: `docs/verification/day0-claude-code-skills.md`

- [ ] **Step 1: Create a throwaway test skill (single-file form)**

Create `~/.claude/skills/relay-test-single/SKILL.md`:

```markdown
---
name: relay-test-single
description: Throwaway skill to verify Claude Code skill loading. Safe to delete.
when_to_use: Never in real work — only used during Relay Week 1 verification
---

# Relay Test Single

If you are reading this, Claude Code successfully loaded a directory-form skill from `~/.claude/skills/relay-test-single/`.
```

- [ ] **Step 2: Create a sidecar file alongside it**

Create `~/.claude/skills/relay-test-single/.relay.yaml`:

```yaml
id: test-sk-001
version: 1
confidence: 0.9
problem:
  symptom: "Testing sibling file tolerance"
```

- [ ] **Step 3: Restart Claude Code and verify the skill is discovered**

Run: `claude /skills list` (or the equivalent; adjust per actual CLI — check `/help`)
Expected: `relay-test-single` appears in the list with no warnings/errors about the `.relay.yaml` sibling.

Record in `docs/verification/day0-claude-code-skills.md`:
- Pass/fail for "directory-form skill loads"
- Pass/fail for "sibling `.relay.yaml` does not break loading"
- Any warnings printed

- [ ] **Step 4: Verify custom frontmatter tolerance**

Edit `~/.claude/skills/relay-test-single/SKILL.md` — add a custom field:

```markdown
---
name: relay-test-single
description: Throwaway skill to verify Claude Code skill loading. Safe to delete.
when_to_use: Never in real work — only used during Relay Week 1 verification
relay_custom_field: "this should be ignored"
---
```

Restart Claude Code, list skills again.

Record:
- Does skill still load? (pass/fail)
- Any warning about unknown field?

If skill fails to load, design decision: `.relay.yaml` sidecar is the ONLY location for Relay metadata. **Our current spec already assumes this**, so failure here is acceptable and confirms the design.

- [ ] **Step 5: Verify description length behavior**

Edit description to ~2000 chars (over the 1536 limit). Reload.

Record whether Claude Code truncates, rejects, or warns.

- [ ] **Step 6: Write verification report**

Create `docs/verification/day0-claude-code-skills.md` with the 4 findings above. Sample:

```markdown
# Day 0 Verification — Claude Code Skills

Date: 2026-04-21
Claude Code version: <output of `claude --version`>

## Findings

| Check | Result | Notes |
|---|---|---|
| Directory-form skill loads | PASS/FAIL | ... |
| Sibling `.relay.yaml` tolerated | PASS/FAIL | ... |
| Custom frontmatter field tolerated | PASS/FAIL | ... |
| Description >1536 chars behavior | truncated/rejected/warned | ... |

## Design Impact
- [bullet points: what stays, what changes]
```

- [ ] **Step 7: Clean up test skill**

Run: `rm -rf ~/.claude/skills/relay-test-single/`

- [ ] **Step 8: Commit verification report**

```bash
cd /Users/dion/potenlab/our_project/relay
git add docs/verification/day0-claude-code-skills.md
git commit -m "docs: add Day 0 Claude Code skill loader verification"
```

**GO/NO-GO gate:** If "Directory-form skill loads" or "Sibling `.relay.yaml` tolerated" fails, STOP and revisit design. Do not proceed to Task 1.

---

## Task 1: Project Skeleton + Git Init

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `local_mcp/__init__.py` (empty)
- Create: `local_mcp/tools/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/dion/potenlab/our_project/relay
git init
git branch -M main
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.env
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
*.log
.DS_Store
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "relay-mcp"
version = "0.1.0"
description = "Local MCP server for Relay — agent skill sharing platform"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=0.1.0",
    "pyyaml>=6.0",
    "python-frontmatter>=1.0.0",
    "pydantic>=2.5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[project.scripts]
relay-mcp = "local_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["local_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 4: Write minimal `README.md`**

```markdown
# Relay

Agent skill sharing platform. See `SPEC.md` for the full MVP spec.

## Week 1: Local MCP + file-based skill storage.

## Install (dev)

    python -m venv .venv && source .venv/bin/activate
    pip install -e ".[dev]"

## Run tests

    pytest
```

- [ ] **Step 5: Create empty package markers**

```bash
touch local_mcp/__init__.py local_mcp/tools/__init__.py tests/__init__.py
```

- [ ] **Step 6: Install and verify package imports**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import local_mcp; print('ok')"
```

Expected output: `ok`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore README.md local_mcp/__init__.py local_mcp/tools/__init__.py tests/__init__.py
git commit -m "chore: initialize relay-mcp project skeleton"
```

---

## Task 2: Domain Types

**Files:**
- Create: `local_mcp/types.py`
- Create: `tests/test_types.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_types.py`:

```python
from datetime import datetime, timezone
import pytest
from local_mcp.types import (
    Attempt,
    ToolUsed,
    Problem,
    Solution,
    RelayMetadata,
)


def test_attempt_failed_case():
    a = Attempt(tried="simple retry", failed_because="ignored Retry-After")
    assert a.tried == "simple retry"
    assert a.failed_because == "ignored Retry-After"
    assert a.worked is None


def test_attempt_worked_case():
    a = Attempt(worked="exponential backoff with header")
    assert a.worked == "exponential backoff with header"
    assert a.tried is None


def test_tool_used_mcp():
    t = ToolUsed(type="mcp", name="stripe")
    assert t.type == "mcp"
    assert t.name == "stripe"


def test_tool_used_invalid_type():
    with pytest.raises(ValueError):
        ToolUsed(type="unknown", name="x")


def test_problem_roundtrip():
    p = Problem(symptom="429 errors", context="checkout")
    as_dict = p.to_dict()
    assert as_dict == {"symptom": "429 errors", "context": "checkout"}
    back = Problem.from_dict(as_dict)
    assert back == p


def test_solution_with_tools():
    s = Solution(
        approach="exponential backoff",
        tools_used=[ToolUsed(type="library", name="tenacity")],
    )
    d = s.to_dict()
    assert d["approach"] == "exponential backoff"
    assert d["tools_used"] == [{"type": "library", "name": "tenacity"}]
    back = Solution.from_dict(d)
    assert back == s


def test_relay_metadata_defaults():
    m = RelayMetadata(
        id="sk_abc",
        source_agent_id="pseudo",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
    )
    assert m.version == 1
    assert m.confidence == 0.5
    assert m.used_count == 0
    assert m.trigger == "manual"
    assert m.status == "active"
    assert m.uploaded is False
    assert m.uploaded_hash is None
    assert m.problem is None


def test_relay_metadata_yaml_roundtrip():
    m = RelayMetadata(
        id="sk_abc",
        source_agent_id="pseudo",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="429", context="checkout"),
        solution=Solution(
            approach="backoff",
            tools_used=[ToolUsed(type="library", name="tenacity")],
        ),
        attempts=[
            Attempt(tried="sleep", failed_because="burst"),
            Attempt(worked="backoff"),
        ],
        context={"languages": ["python"]},
    )
    y = m.to_yaml()
    assert isinstance(y, str)
    back = RelayMetadata.from_yaml(y)
    assert back == m
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_types.py -v
```

Expected: ImportError (types module not yet created).

- [ ] **Step 3: Implement `local_mcp/types.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_types.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add local_mcp/types.py tests/test_types.py
git commit -m "feat(types): add Relay domain types with YAML roundtrip"
```

---

## Task 3: Filesystem Config + Skill Root

**Files:**
- Create: `local_mcp/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_fs.py` (partial — just path logic)

- [ ] **Step 1: Write tests for config + skill-location helpers**

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    """Fresh skill root inside tmp_path; overrides RELAY_SKILL_ROOT."""
    root = tmp_path / "claude-skills"
    root.mkdir()
    monkeypatch.setenv("RELAY_SKILL_ROOT", str(root))
    return root
```

Create `tests/test_fs.py`:

```python
from pathlib import Path
import pytest

from local_mcp.config import get_skill_root
from local_mcp.fs import SkillLocation, skill_dir


def test_get_skill_root_uses_env(skill_root):
    assert get_skill_root() == skill_root


def test_get_skill_root_default(monkeypatch, tmp_path):
    monkeypatch.delenv("RELAY_SKILL_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    root = get_skill_root()
    assert root == tmp_path / ".claude" / "skills"


def test_skill_dir_mine(skill_root):
    d = skill_dir("stripe-rate-limit-handler", SkillLocation.MINE)
    assert d == skill_root / "mine" / "stripe-rate-limit-handler"


def test_skill_dir_downloaded(skill_root):
    d = skill_dir("foo", SkillLocation.DOWNLOADED)
    assert d == skill_root / "downloaded" / "foo"


def test_skill_dir_staging(skill_root):
    d = skill_dir("foo", SkillLocation.STAGING)
    assert d == skill_root / "staging" / "foo"


def test_skill_dir_rejects_path_traversal(skill_root):
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("../evil", SkillLocation.MINE)
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("a/b", SkillLocation.MINE)
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("", SkillLocation.MINE)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_fs.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/config.py`**

```python
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
```

- [ ] **Step 4: Implement `local_mcp/fs.py` (first slice — paths only)**

```python
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
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
pytest tests/test_fs.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add local_mcp/config.py local_mcp/fs.py tests/conftest.py tests/test_fs.py
git commit -m "feat(fs): add skill-root config and path helpers with traversal guard"
```

---

## Task 4: Filesystem — SKILL.md + Sidecar Write/Read

**Files:**
- Modify: `local_mcp/fs.py`
- Modify: `tests/test_fs.py`

- [ ] **Step 1: Add failing tests for write/read**

Append to `tests/test_fs.py`:

```python
from local_mcp.fs import write_skill, read_skill, SkillFiles
from local_mcp.types import RelayMetadata, Problem, Solution, ToolUsed, Attempt


def _sample_metadata() -> RelayMetadata:
    return RelayMetadata(
        id="sk_test",
        source_agent_id="pseudo_xyz",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="429 burst", context="checkout"),
        solution=Solution(
            approach="exponential backoff",
            tools_used=[ToolUsed(type="library", name="tenacity")],
        ),
        attempts=[
            Attempt(tried="sleep 1s", failed_because="still 429"),
            Attempt(worked="backoff header-aware"),
        ],
        context={"languages": ["python"]},
    )


def test_write_skill_creates_both_files(skill_root):
    md_body = "# Body\n\n## Problem\n429 under burst.\n"
    frontmatter = {
        "name": "stripe-rl",
        "description": "Handle 429",
        "when_to_use": "Stripe 429 in checkout",
    }

    files = write_skill(
        name="stripe-rl",
        location=SkillLocation.MINE,
        frontmatter=frontmatter,
        body=md_body,
        metadata=_sample_metadata(),
    )

    assert files.skill_md.exists()
    assert files.relay_yaml.exists()

    raw = files.skill_md.read_text()
    assert "---" in raw
    assert "name: stripe-rl" in raw
    assert "## Problem" in raw

    raw_yaml = files.relay_yaml.read_text()
    assert "id: sk_test" in raw_yaml
    assert "approach: exponential backoff" in raw_yaml


def test_read_skill_roundtrip(skill_root):
    md_body = "# Body\n\n## Problem\nStuff.\n"
    frontmatter = {"name": "stripe-rl", "description": "Handle 429"}
    meta = _sample_metadata()

    write_skill(
        name="stripe-rl",
        location=SkillLocation.MINE,
        frontmatter=frontmatter,
        body=md_body,
        metadata=meta,
    )

    read = read_skill(name="stripe-rl", location=SkillLocation.MINE)
    assert read.frontmatter["name"] == "stripe-rl"
    assert read.frontmatter["description"] == "Handle 429"
    assert read.body.strip() == md_body.strip()
    assert read.metadata == meta


def test_read_skill_missing_raises(skill_root):
    with pytest.raises(FileNotFoundError):
        read_skill(name="does-not-exist", location=SkillLocation.MINE)


def test_write_skill_overwrites(skill_root):
    fm = {"name": "foo", "description": "d"}
    meta = _sample_metadata()
    write_skill(name="foo", location=SkillLocation.MINE,
                frontmatter=fm, body="v1", metadata=meta)
    write_skill(name="foo", location=SkillLocation.MINE,
                frontmatter=fm, body="v2", metadata=meta)

    read = read_skill(name="foo", location=SkillLocation.MINE)
    assert read.body.strip() == "v2"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_fs.py -v
```

Expected: ImportError for `write_skill`, `read_skill`, `SkillFiles`.

- [ ] **Step 3: Extend `local_mcp/fs.py`**

Append to `local_mcp/fs.py`:

```python
from dataclasses import dataclass
from typing import Any

import frontmatter as fm_lib
import yaml

from local_mcp.types import RelayMetadata


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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_fs.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add local_mcp/fs.py tests/test_fs.py
git commit -m "feat(fs): add write_skill and read_skill with sidecar roundtrip"
```

---

## Task 5: Drift Detection

**Files:**
- Create: `local_mcp/drift.py`
- Create: `tests/test_drift.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_drift.py`:

```python
from local_mcp.drift import body_hash, check_drift
from local_mcp.fs import SkillLocation, write_skill, read_skill
from local_mcp.types import RelayMetadata


def test_body_hash_stable():
    h1 = body_hash("some content")
    h2 = body_hash("some content")
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_body_hash_changes_with_content():
    assert body_hash("a") != body_hash("b")


def test_check_drift_no_drift_when_not_uploaded(skill_root):
    meta = RelayMetadata(
        id="sk", source_agent_id="x",
        created_at="t", updated_at="t",
        uploaded=False, uploaded_hash=None,
    )
    write_skill(
        name="foo", location=SkillLocation.MINE,
        frontmatter={"name": "foo", "description": "d"},
        body="hello", metadata=meta,
    )
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert check_drift(loaded) is False


def test_check_drift_detects_edit_after_upload(skill_root):
    body = "original body"
    meta = RelayMetadata(
        id="sk", source_agent_id="x",
        created_at="t", updated_at="t",
        uploaded=True, uploaded_hash=body_hash(body),
    )
    write_skill(
        name="foo", location=SkillLocation.MINE,
        frontmatter={"name": "foo", "description": "d"},
        body=body, metadata=meta,
    )
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert check_drift(loaded) is False

    # Simulate manual edit
    loaded.files.skill_md.write_text(
        loaded.files.skill_md.read_text().replace("original body", "edited body"),
        encoding="utf-8",
    )
    loaded2 = read_skill(name="foo", location=SkillLocation.MINE)
    assert check_drift(loaded2) is True
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_drift.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/drift.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_drift.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add local_mcp/drift.py tests/test_drift.py
git commit -m "feat(drift): detect SKILL.md edits after upload via body hash"
```

---

## Task 6: `skill_capture` Tool (structured input)

**Decision locked in:** `skill_capture` does NOT call an LLM internally. The calling agent (Claude Code) has already seen the session and passes structured inputs. Tool just writes files.

**Files:**
- Create: `local_mcp/tools/capture.py`
- Create: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_capture.py`:

```python
import re

import pytest

from local_mcp.fs import SkillLocation, read_skill
from local_mcp.tools.capture import capture_skill, CaptureInput


def test_capture_writes_both_files(skill_root):
    result = capture_skill(CaptureInput(
        name="stripe-429",
        description="Handle Stripe 429 with exponential backoff",
        when_to_use="Stripe API in high-traffic checkout",
        problem_symptom="429 under burst traffic",
        problem_context="checkout flow",
        solution_approach="exponential backoff with Retry-After",
        attempts=[
            {"tried": "simple retry", "failed_because": "ignored Retry-After"},
            {"tried": "fixed sleep", "failed_because": "still 429"},
            {"worked": "backoff with header"},
        ],
        tools_used=[
            {"type": "library", "name": "tenacity"},
        ],
        languages=["python"],
        libraries=["stripe-python>=8.0"],
        domain="payment",
        body_sections={
            "Problem": "429 under burst.",
            "What I tried": "1. Retry loop — failed\n2. Fixed sleep — failed",
            "What worked": "Exponential backoff with header.",
            "Tools used": "- tenacity",
            "When NOT to use this": "Webhook handlers.",
        },
        source_agent_id="pseudo_xyz",
    ))

    assert result.name == "stripe-429"
    assert result.location == "mine"
    assert result.files.skill_md.exists()
    assert result.files.relay_yaml.exists()

    loaded = read_skill(name="stripe-429", location=SkillLocation.MINE)
    assert loaded.frontmatter["name"] == "stripe-429"
    assert loaded.frontmatter["description"].startswith("Handle Stripe 429")
    assert "## Problem" in loaded.body
    assert "## What I tried" in loaded.body
    assert "## What worked" in loaded.body

    assert loaded.metadata.problem is not None
    assert loaded.metadata.problem.symptom == "429 under burst traffic"
    assert loaded.metadata.solution is not None
    assert loaded.metadata.solution.approach.startswith("exponential backoff")
    assert [a.tried for a in loaded.metadata.attempts[:2]] == [
        "simple retry",
        "fixed sleep",
    ]
    assert loaded.metadata.attempts[2].worked == "backoff with header"
    assert loaded.metadata.source_agent_id == "pseudo_xyz"
    assert loaded.metadata.trigger == "manual"
    assert loaded.metadata.uploaded is False


def test_capture_id_format(skill_root):
    result = capture_skill(CaptureInput(
        name="foo",
        description="d",
        when_to_use="w",
        problem_symptom="s",
        problem_context=None,
        solution_approach="a",
        attempts=[],
        tools_used=[],
        languages=[],
        libraries=[],
        domain=None,
        body_sections={"Problem": "x"},
        source_agent_id="pseudo_xyz",
    ))
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert re.match(r"^sk_[a-z0-9]{16}$", loaded.metadata.id)


def test_capture_rejects_invalid_name(skill_root):
    with pytest.raises(ValueError):
        capture_skill(CaptureInput(
            name="Invalid Name",
            description="d",
            when_to_use="w",
            problem_symptom="s",
            problem_context=None,
            solution_approach="a",
            attempts=[],
            tools_used=[],
            languages=[],
            libraries=[],
            domain=None,
            body_sections={"Problem": "x"},
            source_agent_id="pseudo_xyz",
        ))


def test_capture_with_trigger_override(skill_root):
    capture_skill(CaptureInput(
        name="foo",
        description="d",
        when_to_use="w",
        problem_symptom="s",
        problem_context=None,
        solution_approach="a",
        attempts=[],
        tools_used=[],
        languages=[],
        libraries=[],
        domain=None,
        body_sections={"Problem": "x"},
        source_agent_id="pseudo_xyz",
        trigger="error_recovery",
    ))
    loaded = read_skill(name="foo", location=SkillLocation.MINE)
    assert loaded.metadata.trigger == "error_recovery"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_capture.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/tools/capture.py`**

```python
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_capture.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add local_mcp/tools/capture.py tests/test_capture.py
git commit -m "feat(capture): add skill_capture tool writing SKILL.md + .relay.yaml"
```

---

## Task 7: `skill_list_local` Tool

**Files:**
- Create: `local_mcp/tools/list_local.py`
- Create: `tests/test_list_local.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_list_local.py`:

```python
from local_mcp.fs import SkillLocation, write_skill
from local_mcp.tools.list_local import list_local_skills
from local_mcp.types import RelayMetadata, Problem
from local_mcp.drift import body_hash


def _write(skill_root, name, location, *, body="hello", uploaded=False, upload_body=None):
    h = body_hash(upload_body) if upload_body is not None else None
    meta = RelayMetadata(
        id=f"sk_{name}",
        source_agent_id="x",
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        uploaded=uploaded,
        uploaded_hash=h,
        problem=Problem(symptom=f"{name} symptom"),
        confidence=0.8,
    )
    write_skill(
        name=name,
        location=location,
        frontmatter={"name": name, "description": f"{name} desc"},
        body=body,
        metadata=meta,
    )


def test_list_empty(skill_root):
    assert list_local_skills() == []


def test_list_includes_all_locations(skill_root):
    _write(skill_root, "a", SkillLocation.MINE)
    _write(skill_root, "b", SkillLocation.DOWNLOADED)
    _write(skill_root, "c", SkillLocation.STAGING)

    results = list_local_skills()
    locations = {r["name"]: r["location"] for r in results}
    assert locations == {"a": "mine", "b": "downloaded", "c": "staging"}


def test_list_exposes_symptom_and_confidence(skill_root):
    _write(skill_root, "a", SkillLocation.MINE)
    [r] = list_local_skills()
    assert r["name"] == "a"
    assert r["id"] == "sk_a"
    assert r["symptom"] == "a symptom"
    assert r["confidence"] == 0.8
    assert r["uploaded"] is False
    assert r["drift_detected"] is False


def test_list_detects_drift(skill_root):
    _write(
        skill_root, "a", SkillLocation.MINE,
        body="edited body",
        uploaded=True,
        upload_body="original body",
    )
    [r] = list_local_skills()
    assert r["uploaded"] is True
    assert r["drift_detected"] is True


def test_list_skips_directories_missing_sidecar(skill_root, tmp_path):
    # Create a directory under mine/ without .relay.yaml
    d = skill_root / "mine" / "broken"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: broken\n---\n")
    _write(skill_root, "ok", SkillLocation.MINE)

    results = list_local_skills()
    names = [r["name"] for r in results]
    assert names == ["ok"]
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_list_local.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/tools/list_local.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_list_local.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add local_mcp/tools/list_local.py tests/test_list_local.py
git commit -m "feat(list_local): enumerate skills across mine/downloaded/staging with drift flag"
```

---

## Task 8: FastMCP Server Entry Point

**Files:**
- Create: `local_mcp/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write tests that verify tool registration**

Create `tests/test_server.py`:

```python
import asyncio

import pytest

from local_mcp.server import build_server


@pytest.mark.asyncio
async def test_server_registers_expected_tools(skill_root):
    server = build_server()
    tools = await server.get_tools()
    names = set(tools.keys())
    assert "skill_capture" in names
    assert "skill_list_local" in names


@pytest.mark.asyncio
async def test_capture_tool_end_to_end(skill_root):
    server = build_server()
    tools = await server.get_tools()
    capture = tools["skill_capture"]

    result = await capture.run({
        "name": "foo",
        "description": "d",
        "when_to_use": "w",
        "problem_symptom": "s",
        "problem_context": None,
        "solution_approach": "a",
        "attempts": [],
        "tools_used": [],
        "languages": [],
        "libraries": [],
        "domain": None,
        "body_sections": {"Problem": "x"},
        "source_agent_id": "pseudo",
    })

    # structured_content or content depending on FastMCP version
    payload = result.structured_content or (result.content[0].text if result.content else None)
    assert payload is not None


@pytest.mark.asyncio
async def test_list_tool_end_to_end(skill_root):
    server = build_server()
    tools = await server.get_tools()
    lst = tools["skill_list_local"]

    result = await lst.run({})
    payload = result.structured_content or (result.content[0].text if result.content else None)
    # Empty root → empty list
    assert payload is not None
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/test_server.py -v
```

Expected: ImportError on `build_server`.

- [ ] **Step 3: Implement `local_mcp/server.py`**

```python
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from local_mcp.tools.capture import CaptureInput, capture_skill
from local_mcp.tools.list_local import list_local_skills


def build_server() -> FastMCP:
    mcp = FastMCP("relay")

    @mcp.tool()
    def skill_capture(
        name: str,
        description: str,
        when_to_use: str,
        problem_symptom: str,
        problem_context: str | None,
        solution_approach: str,
        attempts: list[dict[str, Any]],
        tools_used: list[dict[str, Any]],
        languages: list[str],
        libraries: list[str],
        domain: str | None,
        body_sections: dict[str, str],
        source_agent_id: str,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        """Capture a problem-solving session into a local skill directory.

        Writes SKILL.md (Claude Code format) and .relay.yaml (Relay metadata)
        under ~/.claude/skills/mine/<name>/.
        """
        result = capture_skill(CaptureInput(
            name=name,
            description=description,
            when_to_use=when_to_use,
            problem_symptom=problem_symptom,
            problem_context=problem_context,
            solution_approach=solution_approach,
            attempts=attempts,
            tools_used=tools_used,
            languages=languages,
            libraries=libraries,
            domain=domain,
            body_sections=body_sections,
            source_agent_id=source_agent_id,
            trigger=trigger,
        ))
        return {
            "id": result.id,
            "name": result.name,
            "location": result.location,
            "skill_md_path": str(result.files.skill_md),
            "relay_yaml_path": str(result.files.relay_yaml),
        }

    @mcp.tool()
    def skill_list_local() -> list[dict[str, Any]]:
        """List every Relay-managed skill under ~/.claude/skills/."""
        return list_local_skills()

    return mcp


def main() -> None:
    server = build_server()
    server.run()  # default: stdio


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_server.py -v
```

Expected: 3 tests pass.

Notes:
- If FastMCP's `get_tools()` or `.run({...})` shape differs from the assumption, **read FastMCP docs/source** and adjust the test to match. Do NOT change the production code to work around tests unless the behavior is wrong.

- [ ] **Step 5: Run the full suite**

```bash
pytest -v
```

Expected: all tests pass across all files.

- [ ] **Step 6: Smoke-run the server via stdio**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | relay-mcp 2>&1 | head -20
```

Expected: JSON response listing `skill_capture` and `skill_list_local`. If the CLI hangs waiting for more messages that is also acceptable — kill it (Ctrl-C). The key evidence is that the JSON listing appears.

- [ ] **Step 7: Commit**

```bash
git add local_mcp/server.py tests/test_server.py
git commit -m "feat(server): expose skill_capture and skill_list_local via FastMCP stdio"
```

---

## Task 9: Claude Code Plugin Adapter

**Files:**
- Create: `adapters/claude/.claude-plugin/plugin.json`
- Create: `adapters/claude/SKILL.md`
- Create: `adapters/claude/commands/relay-capture.md`

- [ ] **Step 1: Write the plugin manifest**

Create `adapters/claude/.claude-plugin/plugin.json`:

```json
{
  "name": "relay",
  "version": "0.1.0",
  "description": "Relay — agent skill sharing (Week 1: local capture + list)",
  "mcpServers": {
    "relay": {
      "command": "relay-mcp",
      "args": []
    }
  }
}
```

- [ ] **Step 2: Write the agent-behavior SKILL.md**

Create `adapters/claude/SKILL.md`:

```markdown
---
name: relay
description: Capture and list problem-solving skills. Use when you just recovered from an error, when the user asks to save an approach, or when starting a difficult task and want to check for prior art.
when_to_use: After recovering from non-trivial errors, or when the user says save this / remember this / capture this
---

# Relay Agent Behavior

You have access to Relay's local MCP tools. Week 1 scope: `skill_capture`, `skill_list_local`.

## When to capture

Call `skill_capture` after one of these:
1. You just recovered from an error by trying multiple approaches.
2. The user explicitly asked to save the approach ("save this as a skill", "capture this").
3. A session produced a non-obvious solution worth preserving.

## How to call `skill_capture`

Collect these from the conversation BEFORE calling:
- **name**: kebab-case, e.g. `stripe-rate-limit-handler`.
- **description**: one-line, searchable, <200 chars.
- **when_to_use**: a sentence describing when this applies.
- **problem_symptom / problem_context**: what was observed.
- **solution_approach**: one sentence describing what worked.
- **attempts**: list of `{tried, failed_because}` for each failure, plus one `{worked}` entry at the end.
- **tools_used**: list of `{type: "mcp" | "library" | "cli", name}`.
- **languages / libraries / domain**: free-form lists.
- **body_sections**: a mapping from heading to markdown text. Always include at minimum `Problem`, `What I tried`, `What worked`, `Tools used`, `When NOT to use this`.

⚠️ Never omit failed attempts. The failure log is the most valuable part of a skill.
⚠️ Never write "this works" as solution body. Always narrate: "I tried X, failed because Y, then Z worked because …"

## After capture

Tell the user:
- The path to the new skill.
- That it is local only (not uploaded). Upload will be a separate step in future Relay weeks.

## Listing existing skills

Call `skill_list_local` when:
- User asks "what have I saved?"
- You want to show drift warnings before making changes.
```

- [ ] **Step 3: Write the slash command**

Create `adapters/claude/commands/relay-capture.md`:

```markdown
---
name: relay:capture
description: Manually capture the current session as a Relay skill
---

You are about to call the `skill_capture` MCP tool.

Before calling:
1. Summarize the problem just solved.
2. List every failed attempt with its failure reason.
3. State the solution clearly.
4. Propose a kebab-case skill name.
5. Confirm with the user before writing.

Then call `skill_capture` with all required fields. Afterwards, show the user the resulting paths.
```

- [ ] **Step 4: Manual install and smoke test**

```bash
# Ensure relay-mcp is on PATH in the Claude Code environment
which relay-mcp
```

Link/copy the plugin into Claude Code's plugin directory (exact path depends on Claude Code's current plugin model — check `claude /help` or docs):

```bash
# Example (adjust per actual Claude Code plugin-install mechanism)
ln -s "$(pwd)/adapters/claude" ~/.claude/plugins/relay
```

Restart Claude Code, then in a session run:

```
/relay:capture
```

Verify:
- Slash command is discovered.
- The MCP tools `skill_capture` and `skill_list_local` are available.

Record findings in `docs/verification/day0-claude-code-skills.md` under a new "Plugin install" section.

- [ ] **Step 5: Commit**

```bash
git add adapters/claude docs/verification/day0-claude-code-skills.md
git commit -m "feat(adapter/claude): add plugin manifest, SKILL.md and /relay:capture command"
```

---

## Task 10: End-to-End Smoke Test

**Goal:** Prove the full loop — plugin → MCP tool → filesystem → Claude Code discovery — works on a real skill.

**Files:**
- Modify: `docs/verification/day0-claude-code-skills.md`

- [ ] **Step 1: Start a fresh Claude Code session**

Open Claude Code in any directory and say:

> I just solved a Stripe 429 problem. First I tried a simple retry loop — it ignored Retry-After and got banned for 10 minutes. Then I tried a fixed 1-second sleep — still rate-limited under burst. Finally I used exponential backoff with the Retry-After header and it worked. I used the tenacity library. Please save this as a skill called `stripe-rate-limit-handler`.

- [ ] **Step 2: Verify skill files were created**

```bash
ls -la ~/.claude/skills/mine/stripe-rate-limit-handler/
cat ~/.claude/skills/mine/stripe-rate-limit-handler/SKILL.md
cat ~/.claude/skills/mine/stripe-rate-limit-handler/.relay.yaml
```

Expected:
- Both files exist.
- `SKILL.md` has `name`, `description`, `when_to_use` frontmatter + body with Problem / What I tried / What worked / Tools used / When NOT to use this.
- `.relay.yaml` has `id`, `problem.symptom`, `solution.approach`, `attempts` with 3 entries (2 failures + 1 worked).

- [ ] **Step 3: Restart Claude Code and verify auto-discovery**

In a new Claude Code session, without re-explaining, say:

> Does the stripe-rate-limit-handler skill apply if I am about to call Stripe API again?

Expected: Claude Code activates the skill (you can see it referenced or its content informs the answer).

- [ ] **Step 4: Call `skill_list_local`**

In Claude Code:

> List every Relay skill I have locally.

Expected: The list includes `stripe-rate-limit-handler` with `location: mine`, `uploaded: false`, `drift_detected: false`, and the expected `symptom`.

- [ ] **Step 5: Introduce drift**

Open `~/.claude/skills/mine/stripe-rate-limit-handler/SKILL.md` in an editor and change one line. In Claude Code:

> List skills again.

Expected:
- `uploaded: false` still → `drift_detected: false` (drift only fires when uploaded). That confirms drift is only meaningful post-upload.

- [ ] **Step 6: Simulate upload state and re-check drift**

Manually edit `~/.claude/skills/mine/stripe-rate-limit-handler/.relay.yaml`:

```yaml
uploaded: true
uploaded_hash: "0000000000000000000000000000000000000000000000000000000000000000"  # fake, won't match
```

In Claude Code:

> List skills again.

Expected: `drift_detected: true` for this skill.

- [ ] **Step 7: Update the verification doc**

Append to `docs/verification/day0-claude-code-skills.md`:

```markdown
## End-to-end smoke test (Task 10)

Date: 2026-04-21
Result: PASS/FAIL

Checks:
- [ ] skill_capture writes both files
- [ ] Claude Code auto-discovers the new skill after restart
- [ ] skill_list_local enumerates it
- [ ] drift detection flips to true when uploaded_hash mismatches body

Observed issues: …
```

- [ ] **Step 8: Clean up and commit**

```bash
# Keep the test skill if useful; otherwise remove
# rm -rf ~/.claude/skills/mine/stripe-rate-limit-handler/

git add docs/verification/day0-claude-code-skills.md
git commit -m "docs: record Week 1 end-to-end smoke test results"
```

---

## Exit Criteria for Week 1

All of the following must be true:

1. `pytest` passes cleanly with every test from Tasks 2–8.
2. Task 0 verification report exists and shows:
   - Directory-form skill loads ✓
   - `.relay.yaml` sibling tolerated ✓
3. Task 10 smoke test passes end-to-end.
4. The Claude Code plugin can be installed and `/relay:capture` works in a live session.
5. `git log --oneline` shows incremental commits per task (no squashed "week 1 done" commit).

If any item fails, record the failure in `docs/verification/day0-claude-code-skills.md` and stop before starting Week 2.

---

## Self-review — performed

- **Spec coverage:** This plan implements SPEC Section 3.1 (skill layout), 3.3 (mine/downloaded/staging), 4.1 (`skill_capture` — structured-input variant), 4.6 (`skill_list_local`), Section 6 (Claude adapter), Section 8 Week 1 roadmap. It defers 4.2 (`skill_upload`), 4.3 (`skill_search`), 4.4 (`skill_fetch`), 4.5 (`skill_review`), all central-API work, PII masking, embedding, and auto-trigger hooks to Week 2+.
- **Placeholder scan:** No "TBD" / "implement later" / "similar to Task N" references remain. Every step has code or exact commands.
- **Type consistency:** `CaptureInput`, `CaptureResult`, `SkillFiles`, `LoadedSkill`, `SkillLocation`, `RelayMetadata`, `Problem`, `Solution`, `Attempt`, `ToolUsed` are defined once and referenced consistently. `list_local_skills` returns `list[dict[str, Any]]` with a documented shape. `build_server` name is consistent across tasks.

import pytest

from local_mcp.config import get_skill_root
from local_mcp.fs import SkillFiles, SkillLocation, read_skill, skill_dir, write_skill
from local_mcp.types import Attempt, Problem, RelayMetadata, Solution, ToolUsed


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


def test_skill_dir_rejects_path_traversal(skill_root):
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("../evil", SkillLocation.MINE)
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("a/b", SkillLocation.MINE)
    with pytest.raises(ValueError, match="invalid skill name"):
        skill_dir("", SkillLocation.MINE)


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


def test_write_skill_creates_activation_symlink(skill_root):
    """After write_skill, ~/.claude/skills/<name> must be a symlink to the real dir
    so Claude Code's flat scanner can find SKILL.md."""
    fm = {"name": "linkme", "description": "d"}
    files = write_skill(
        name="linkme", location=SkillLocation.MINE,
        frontmatter=fm, body="body", metadata=_sample_metadata(),
    )

    link = skill_root / "linkme"
    assert link.is_symlink()
    assert link.resolve() == files.dir.resolve()
    # Claude Code should see SKILL.md through the flat link.
    assert (link / "SKILL.md").exists()


def test_write_skill_replaces_stale_symlink(skill_root):
    """Re-writing a skill must refresh the symlink (idempotent)."""
    fm = {"name": "refresh", "description": "d"}
    meta = _sample_metadata()
    write_skill(name="refresh", location=SkillLocation.MINE,
                frontmatter=fm, body="v1", metadata=meta)
    # Simulate: skill moved from mine → downloaded (e.g. fetch after capture).
    write_skill(name="refresh", location=SkillLocation.DOWNLOADED,
                frontmatter=fm, body="v2", metadata=meta)

    link = skill_root / "refresh"
    assert link.is_symlink()
    assert link.resolve() == (skill_root / "downloaded" / "refresh").resolve()


def test_write_skill_overwrites(skill_root):
    fm = {"name": "foo", "description": "d"}
    meta = _sample_metadata()
    write_skill(name="foo", location=SkillLocation.MINE,
                frontmatter=fm, body="v1", metadata=meta)
    write_skill(name="foo", location=SkillLocation.MINE,
                frontmatter=fm, body="v2", metadata=meta)

    read = read_skill(name="foo", location=SkillLocation.MINE)
    assert read.body.strip() == "v2"

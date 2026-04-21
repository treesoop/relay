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

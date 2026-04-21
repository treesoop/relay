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

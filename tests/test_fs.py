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

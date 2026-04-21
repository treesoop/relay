import pytest


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    """Fresh skill root inside tmp_path; overrides RELAY_SKILL_ROOT."""
    root = tmp_path / "claude-skills"
    root.mkdir()
    monkeypatch.setenv("RELAY_SKILL_ROOT", str(root))
    return root

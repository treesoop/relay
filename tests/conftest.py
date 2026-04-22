import pytest


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    """Fresh skill root inside tmp_path; overrides RELAY_SKILL_ROOT."""
    root = tmp_path / "claude-skills"
    root.mkdir()
    monkeypatch.setenv("RELAY_SKILL_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def isolated_credentials(tmp_path, monkeypatch):
    """Every test gets its own credentials.json so secrets don't leak across tests."""
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("RELAY_CREDENTIALS_PATH", str(path))
    return path

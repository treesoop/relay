import os
import time

import httpx
import pytest

from local_mcp.fs import SkillLocation, read_skill, write_skill
from local_mcp.tools.fetch import FetchInput, fetch_skill
from local_mcp.tools.upload import UploadInput, upload_skill
from local_mcp.types import Problem, RelayMetadata, Solution


pytestmark = pytest.mark.skipif(
    os.environ.get("RELAY_RUN_E2E") != "1",
    reason="opt-in: set RELAY_RUN_E2E=1 to run (requires docker compose up)",
)


API_URL = os.environ.get("RELAY_API_URL", "http://localhost:8080")
AGENT_ID = "e2e-agent"


def _wait_for_api(timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_URL}/health", timeout=1.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"API at {API_URL} did not become ready in {timeout}s")


@pytest.mark.asyncio
async def test_upload_then_fetch_roundtrip(skill_root):
    _wait_for_api()

    # Write a local skill.
    meta = RelayMetadata(
        id="sk_local",
        source_agent_id=AGENT_ID,
        created_at="2026-04-21T10:00:00Z",
        updated_at="2026-04-21T10:00:00Z",
        problem=Problem(symptom="e2e test symptom"),
        solution=Solution(approach="e2e approach", tools_used=[]),
        context={"languages": ["python"], "libraries": []},
    )
    write_skill(
        name="e2e-test",
        location=SkillLocation.MINE,
        frontmatter={"name": "e2e-test", "description": "e2e", "when_to_use": "never"},
        body="body with alice@example.com for masking",
        metadata=meta,
    )

    # Upload.
    up = await upload_skill(UploadInput(
        name="e2e-test", api_url=API_URL, agent_id=AGENT_ID,
    ))
    remote_id = up.remote_id
    assert remote_id.startswith("sk_")

    # Local file should now be flagged uploaded.
    local = read_skill(name="e2e-test", location=SkillLocation.MINE)
    assert local.metadata.uploaded is True
    assert "[REDACTED:email]" in local.body

    # Fetch the same skill back into downloaded/.
    f = await fetch_skill(FetchInput(
        skill_id=remote_id, api_url=API_URL, agent_id=AGENT_ID,
    ))
    downloaded = read_skill(name=f.name, location=SkillLocation.DOWNLOADED)
    assert downloaded.metadata.id == remote_id
    assert "[REDACTED:email]" in downloaded.body

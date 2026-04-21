# Relay Week 3 — Reviews + Auto-Capture + Stale Lifecycle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the feedback loop that keeps the commons healthy — `skill_review` (good/bad/stale), confidence re-scoring on every review, auto-stale transition after 3 stale reviews, and a best-effort Claude Code error-recovery hook that fires `skill_capture` at the right moment. Exit criterion: uploading a skill, reviewing it bad three times with `reason=stale` flips `status` to `stale`, and search results exclude stale skills.

**Architecture:**
- **Central API:** new `POST /skills/{id}/reviews` router — accepts `{signal, reason, note}` from the authenticated agent, inserts a row, recomputes `confidence` = `(good + 0.5) / (good + bad + 1)`, increments `good_count`/`bad_count` based on signal, and flips `status` to `stale` if ≥3 `signal=stale` reviews exist. Search (`GET /skills/search`) already filters `status='active'`, so stale skills naturally disappear from results.
- **Local MCP:** new `skill_review` tool wraps the HTTP POST. After a successful fetch + use session, agents call `skill_review` with `good`/`bad`/`stale`. `reason` is optional free-form (MVP — constrained vocabularies come later).
- **Auto-capture hook (Claude Code only):** thin `hooks.json` + a small shell helper that triggers `skill_capture` when a `PostToolUse` sequence detects "error → retry → success" within a session. Best-effort — noisy hooks are worse than no hooks, so the detection is conservative (tool-call error rate > 0, final tool succeeded, no error in last N=3 calls).
- **Unchanged:** embedding provider (local BGE), ranking formula, capture/list_local/upload/fetch semantics.

**Tech Stack:**
- No new Python deps. New SQL migration (`central_api/sql/002_reviews_trigger.sql`) adds a Postgres function for confidence re-scoring (keeps the logic authoritative at the DB level).
- Claude Code hooks are shell scripts in `adapters/claude/hooks/`.

---

## File Structure

```
relay/
├── central_api/
│   ├── sql/
│   │   └── 002_reviews_trigger.sql          # NEW: confidence recompute + auto-stale function
│   ├── routers/
│   │   └── reviews.py                       # NEW: POST /skills/{id}/reviews
│   ├── main.py                              # MODIFY: include reviews_router
│   ├── schemas.py                           # MODIFY: add ReviewRequest, ReviewResponse
│   └── tests/
│       ├── test_api_reviews.py              # NEW: post-review behavior, confidence recompute, auto-stale
│       └── (unchanged)
│
├── local_mcp/
│   ├── tools/
│   │   └── review.py                        # NEW: skill_review MCP tool
│   └── server.py                            # MODIFY: register skill_review
│
├── tests/
│   ├── test_review.py                       # NEW: mocked httpx review tool
│   └── test_server.py                       # MODIFY: assert skill_review registered
│
├── adapters/claude/
│   ├── hooks.json                           # NEW: error-recovery detection config
│   ├── hooks/
│   │   └── post-tool-use.sh                 # NEW: shell detector invoked by Claude Code
│   └── SKILL.md                             # MODIFY: document when to call skill_review
│
├── deploy/
│   └── 02-rds-init.sh                       # MODIFY: also apply 002_reviews_trigger.sql
│
└── docs/
    └── superpowers/plans/
        └── 2026-04-22-week3-reviews-auto-capture.md   # this file
```

---

## Task 0: SQL — reviews trigger + confidence recompute

**Files:**
- Create: `central_api/sql/002_reviews_trigger.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Recompute confidence = (good + 0.5) / (good + bad + 1) and flip status='stale'
-- when we've accumulated >= 3 stale signals. Single source of truth at the DB level.

CREATE OR REPLACE FUNCTION relay_apply_review()
RETURNS TRIGGER AS $$
DECLARE
    g INT;
    b INT;
    s INT;
BEGIN
    IF NEW.signal = 'good' THEN
        UPDATE skills SET good_count = good_count + 1 WHERE id = NEW.skill_id;
    ELSIF NEW.signal = 'bad' THEN
        UPDATE skills SET bad_count = bad_count + 1 WHERE id = NEW.skill_id;
    END IF;

    SELECT good_count, bad_count INTO g, b FROM skills WHERE id = NEW.skill_id;
    UPDATE skills
       SET confidence = (g + 0.5) / GREATEST(g + b + 1, 1),
           updated_at = NOW()
     WHERE id = NEW.skill_id;

    -- Auto-stale: 3+ stale signals → status=stale
    SELECT COUNT(*) INTO s FROM reviews WHERE skill_id = NEW.skill_id AND signal = 'stale';
    IF s >= 3 THEN
        UPDATE skills SET status = 'stale' WHERE id = NEW.skill_id AND status = 'active';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reviews_apply_trigger ON reviews;
CREATE TRIGGER reviews_apply_trigger
    AFTER INSERT ON reviews
    FOR EACH ROW
    EXECUTE FUNCTION relay_apply_review();
```

- [ ] **Step 2: Apply to local docker postgres**

```bash
cd /Users/dion/potenlab/our_project/relay
docker compose exec -T postgres psql -U relay -d relay -f - < central_api/sql/002_reviews_trigger.sql
docker compose exec -T postgres psql -U relay -d relay -c "\df relay_apply_review"
```

Expected: `CREATE FUNCTION` + `CREATE TRIGGER` ack; `\df` shows the function exists.

- [ ] **Step 3: Apply to RDS**

```bash
ENDPOINT=$(jq -r .db_endpoint .aws/deployment-state.json)
USER=$(jq -r .db_user .aws/deployment-state.json)
NAME=$(jq -r .db_name .aws/deployment-state.json)
PASS=$(jq -r .db_password .aws/deployment-state.json)
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -v ON_ERROR_STOP=1 -f central_api/sql/002_reviews_trigger.sql
```

- [ ] **Step 4: Commit**

```bash
git add central_api/sql/002_reviews_trigger.sql
git commit -m "feat(api): reviews trigger — recompute confidence + auto-stale at >=3 stale reviews"
```

---

## Task 1: POST /skills/{id}/reviews endpoint

**Files:**
- Modify: `central_api/schemas.py` (add `ReviewRequest`, `ReviewResponse`)
- Create: `central_api/routers/reviews.py`
- Modify: `central_api/main.py` (include router)
- Create: `central_api/tests/test_api_reviews.py`

- [ ] **Step 1: Write failing tests**

Create `central_api/tests/test_api_reviews.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from central_api.db import get_session
from central_api.embedding import StubEmbedder
from central_api.main import create_app


@pytest.fixture
def app(db_session):
    app = create_app(embedder=StubEmbedder())

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    return app


async def _seed_skill(client: AsyncClient, agent: str = "uploader") -> str:
    await client.post("/auth/register", json={"agent_id": agent})
    r = await client.post("/skills", json={
        "name": "r-skill", "description": "d", "when_to_use": "w", "body": "b",
        "metadata": {
            "problem": {"symptom": "x"},
            "solution": {"approach": "y", "tools_used": []},
            "attempts": [],
            "context": {"languages": [], "libraries": []},
        },
    }, headers={"X-Relay-Agent-Id": agent})
    return r.json()["id"]


@pytest.mark.asyncio
async def test_post_review_good_updates_counts(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        await client.post("/auth/register", json={"agent_id": "reviewer"})

        r = await client.post(f"/skills/{sid}/reviews", json={"signal": "good"},
                              headers={"X-Relay-Agent-Id": "reviewer"})
        assert r.status_code == 201, r.text

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "reviewer"})).json()
        assert s["good_count"] == 1
        assert s["bad_count"] == 0
        # confidence = (1 + 0.5) / (1 + 0 + 1) = 0.75
        assert abs(s["confidence"] - 0.75) < 1e-6


@pytest.mark.asyncio
async def test_post_review_bad_updates_counts(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        await client.post("/auth/register", json={"agent_id": "reviewer"})

        r = await client.post(f"/skills/{sid}/reviews",
                              json={"signal": "bad", "reason": "api_changed"},
                              headers={"X-Relay-Agent-Id": "reviewer"})
        assert r.status_code == 201

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "reviewer"})).json()
        assert s["good_count"] == 0
        assert s["bad_count"] == 1
        # (0 + 0.5) / (0 + 1 + 1) = 0.25
        assert abs(s["confidence"] - 0.25) < 1e-6


@pytest.mark.asyncio
async def test_three_stale_reviews_flip_status(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        for agent in ("r1", "r2", "r3"):
            await client.post("/auth/register", json={"agent_id": agent})
            r = await client.post(f"/skills/{sid}/reviews", json={"signal": "stale"},
                                  headers={"X-Relay-Agent-Id": agent})
            assert r.status_code == 201

        s = (await client.get(f"/skills/{sid}", headers={"X-Relay-Agent-Id": "r1"})).json()
        assert s["status"] == "stale"


@pytest.mark.asyncio
async def test_stale_skill_excluded_from_search(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        for agent in ("r1", "r2", "r3"):
            await client.post("/auth/register", json={"agent_id": agent})
            await client.post(f"/skills/{sid}/reviews", json={"signal": "stale"},
                              headers={"X-Relay-Agent-Id": agent})

        r = await client.get("/skills/search",
                             params={"query": "x", "search_mode": "problem"},
                             headers={"X-Relay-Agent-Id": "r1"})
        items = r.json()["items"]
        assert all(it["skill"]["id"] != sid for it in items)


@pytest.mark.asyncio
async def test_invalid_signal_rejected(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sid = await _seed_skill(client)
        await client.post("/auth/register", json={"agent_id": "r"})
        r = await client.post(f"/skills/{sid}/reviews", json={"signal": "bogus"},
                              headers={"X-Relay-Agent-Id": "r"})
        assert r.status_code == 422  # pydantic rejects enum value


@pytest.mark.asyncio
async def test_review_on_missing_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/auth/register", json={"agent_id": "r"})
        r = await client.post("/skills/sk_nope/reviews", json={"signal": "good"},
                              headers={"X-Relay-Agent-Id": "r"})
        assert r.status_code == 404
```

- [ ] **Step 2: Run to confirm fail**

```bash
cd /Users/dion/potenlab/our_project/relay
source .venv/bin/activate
pytest central_api/tests/test_api_reviews.py -v
```

Expected: ImportError (reviews router + schemas missing).

- [ ] **Step 3: Extend `central_api/schemas.py`**

Append to `central_api/schemas.py`:

```python
from typing import Literal

ReviewSignal = Literal["good", "bad", "stale"]


class ReviewRequest(BaseModel):
    signal: ReviewSignal
    reason: str | None = None
    note: str | None = None


class ReviewResponse(BaseModel):
    id: int
    skill_id: str
    agent_id: str
    signal: ReviewSignal
    reason: str | None
    note: str | None
```

- [ ] **Step 4: Implement `central_api/routers/reviews.py`**

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from central_api.auth import require_agent_id
from central_api.db import get_session
from central_api.models import Review, Skill
from central_api.schemas import ReviewRequest, ReviewResponse


router = APIRouter(prefix="/skills", tags=["reviews"])


@router.post(
    "/{skill_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_review(
    skill_id: str,
    body: ReviewRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    agent_id: Annotated[str, Depends(require_agent_id)],
) -> ReviewResponse:
    skill = await session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")

    review = Review(
        skill_id=skill_id,
        agent_id=agent_id,
        signal=body.signal,
        reason=body.reason,
        note=body.note,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)

    return ReviewResponse(
        id=review.id,
        skill_id=review.skill_id,
        agent_id=review.agent_id,
        signal=review.signal,  # type: ignore[arg-type]
        reason=review.reason,
        note=review.note,
    )
```

- [ ] **Step 5: Wire the router in `central_api/main.py`**

Add to the imports:
```python
from central_api.routers.reviews import router as reviews_router
```

And inside `create_app`, after `app.include_router(skills_router)`:
```python
app.include_router(reviews_router)
```

- [ ] **Step 6: Run tests to confirm pass**

The trigger must already be installed (Task 0). The tests rely on it for confidence recomputation.

```bash
pytest central_api/tests/test_api_reviews.py -v
```

Expected: 6 passed. If the auto-stale test fails, verify the trigger is present: `docker compose exec -T postgres psql -U relay -d relay -c "\df relay_apply_review"`.

- [ ] **Step 7: Full suite**

```bash
pytest -v
```

Expected: existing 84 passed + 6 new = 90 passed, 1 skipped.

- [ ] **Step 8: Commit**

```bash
git add central_api/schemas.py central_api/routers/reviews.py central_api/main.py central_api/tests/test_api_reviews.py
git commit -m "feat(api): POST /skills/{id}/reviews + confidence recompute + auto-stale"
```

---

## Task 2: Local MCP `skill_review` tool

**Files:**
- Create: `local_mcp/tools/review.py`
- Create: `tests/test_review.py`
- Modify: `local_mcp/server.py` (register)
- Modify: `tests/test_server.py` (assert registration)

- [ ] **Step 1: Write failing tests**

Create `tests/test_review.py`:

```python
import httpx
import pytest

from local_mcp.tools.review import ReviewInput, review_skill


@pytest.fixture
def fake_api(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/skills/sk_abc/reviews" and request.method == "POST":
            body = request.read().decode()
            return httpx.Response(201, json={
                "id": 1,
                "skill_id": "sk_abc",
                "agent_id": "me",
                "signal": "good",
                "reason": None,
                "note": None,
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("local_mcp.tools.review._build_transport", lambda: transport)


@pytest.mark.asyncio
async def test_review_good_succeeds(fake_api):
    result = await review_skill(ReviewInput(
        skill_id="sk_abc", api_url="http://test", agent_id="me", signal="good",
    ))
    assert result.review_id == 1
    assert result.skill_id == "sk_abc"


@pytest.mark.asyncio
async def test_review_with_reason_and_note(fake_api):
    result = await review_skill(ReviewInput(
        skill_id="sk_abc", api_url="http://test", agent_id="me",
        signal="good", reason="worked as described", note="saved 20 min",
    ))
    assert result.skill_id == "sk_abc"


@pytest.mark.asyncio
async def test_review_missing_skill_raises(fake_api):
    with pytest.raises(httpx.HTTPStatusError):
        await review_skill(ReviewInput(
            skill_id="sk_nope", api_url="http://test", agent_id="me", signal="good",
        ))
```

- [ ] **Step 2: Run to confirm fail**

```bash
pytest tests/test_review.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `local_mcp/tools/review.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


Signal = Literal["good", "bad", "stale"]


@dataclass
class ReviewInput:
    skill_id: str
    api_url: str
    agent_id: str
    signal: Signal
    reason: str | None = None
    note: str | None = None


@dataclass
class ReviewResult:
    review_id: int
    skill_id: str


def _build_transport() -> httpx.BaseTransport | None:
    return None


async def review_skill(inp: ReviewInput) -> ReviewResult:
    payload: dict[str, str | None] = {"signal": inp.signal}
    if inp.reason is not None:
        payload["reason"] = inp.reason
    if inp.note is not None:
        payload["note"] = inp.note

    transport = _build_transport()
    async with httpx.AsyncClient(
        base_url=inp.api_url,
        headers={"X-Relay-Agent-Id": inp.agent_id},
        transport=transport,
        timeout=30.0,
    ) as client:
        resp = await client.post(f"/skills/{inp.skill_id}/reviews", json=payload)
        resp.raise_for_status()
        data = resp.json()

    return ReviewResult(review_id=data["id"], skill_id=data["skill_id"])
```

- [ ] **Step 4: Run to confirm pass**

```bash
pytest tests/test_review.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Register in `local_mcp/server.py`**

Add import:
```python
from local_mcp.tools.review import ReviewInput, review_skill
```

Inside `build_server()`, add after `skill_fetch`:
```python
    @mcp.tool()
    async def skill_review(
        skill_id: str,
        api_url: str,
        agent_id: str,
        signal: str,
        reason: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        """Submit a review (good/bad/stale) for a central Relay skill.

        Triggers server-side confidence recompute and may auto-stale the skill
        after 3 stale signals.
        """
        result = await review_skill(ReviewInput(
            skill_id=skill_id, api_url=api_url, agent_id=agent_id,
            signal=signal,  # type: ignore[arg-type]
            reason=reason, note=note,
        ))
        return {"review_id": result.review_id, "skill_id": result.skill_id}
```

- [ ] **Step 6: Extend `tests/test_server.py`**

Add `assert "skill_review" in names` to `test_server_registers_expected_tools`.

- [ ] **Step 7: Full suite**

```bash
pytest -v
```

Expected: 93 passed, 1 skipped (90 after Task 1 + 3 new).

- [ ] **Step 8: Commit**

```bash
git add local_mcp/tools/review.py tests/test_review.py local_mcp/server.py tests/test_server.py
git commit -m "feat(mcp): skill_review tool — POST /skills/{id}/reviews via httpx"
```

---

## Task 3: Update Claude Code adapter

**Files:**
- Modify: `adapters/claude/SKILL.md` (document skill_review usage)

- [ ] **Step 1: Update SKILL.md**

Find the "After capture" section in `adapters/claude/SKILL.md` and add a new section below it:

```markdown
## After using a fetched skill

When you've used a skill fetched from the Relay commons (skills under `~/.claude/skills/downloaded/`), call `skill_review` once the work is done:

- `signal="good"`: skill applied cleanly to your situation and the approach worked.
- `signal="bad"`: skill was technically valid but didn't apply (wrong context, outdated library, unclear). Supply `reason` if you can ("api_changed", "context_mismatch", "low_quality").
- `signal="stale"`: skill references something that no longer exists or is wrong. After three stale reviews the commons flips the skill to `status=stale` and excludes it from search.

Keep reviews short. One honest signal per use; don't inflate counts.
```

- [ ] **Step 2: Commit**

```bash
git add adapters/claude/SKILL.md
git commit -m "docs(adapter/claude): document skill_review usage for agents"
```

---

## Task 4: Error-recovery auto-capture hook (best-effort)

**Files:**
- Create: `adapters/claude/hooks.json`
- Create: `adapters/claude/hooks/post-tool-use.sh`

**Scope caveat:** Claude Code's hook event model has changed between versions; this task ships a **best-effort** hook that emits a suggestion (not an automatic capture). The hook writes to a small JSON log at `~/.relay-hook-state.json`, which the next-turn agent reads via a tip at SessionStart. Actual auto-capture remains manual for MVP until we validate the hook reliably fires on real error-recovery sessions.

- [ ] **Step 1: Write the hook script**

Create `adapters/claude/hooks/post-tool-use.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Claude Code invokes this with JSON on stdin containing tool-call metadata.
# We maintain a tiny sliding window of recent errors per session and set a
# "capture suggestion" flag when we see recovery (error followed by success).

STATE="$HOME/.relay-hook-state.json"
[ -f "$STATE" ] || echo '{"errors_recent": 0, "last_status": "unknown", "suggest_capture": false}' > "$STATE"

INPUT=$(cat)
# Minimal parsing: treat any non-zero exit or "error" keyword in result as an error.
IS_ERROR=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d.get("result") or {}; print("true" if r.get("error") else "false")' 2>/dev/null || echo "false")

python3 - "$STATE" "$IS_ERROR" <<'PY'
import json, sys
p, is_error = sys.argv[1], sys.argv[2] == "true"
st = json.load(open(p))
if is_error:
    st["errors_recent"] = min(st.get("errors_recent", 0) + 1, 10)
    st["last_status"] = "error"
    st["suggest_capture"] = False
else:
    # Recovery detected: at least one recent error and we just succeeded.
    st["suggest_capture"] = st.get("errors_recent", 0) >= 1 and st.get("last_status") == "error"
    st["last_status"] = "ok"
    st["errors_recent"] = 0
json.dump(st, open(p, "w"))
PY
```

`chmod +x adapters/claude/hooks/post-tool-use.sh`.

- [ ] **Step 2: Write `hooks.json`**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/plugins/cache/relay-local/relay/adapters/claude/hooks/post-tool-use.sh"
          }
        ]
      }
    ]
  }
}
```

**Important:** the path in `command` depends on where the plugin was installed. For `claude plugin install relay@relay-local` from our local marketplace, the adapter lives under `~/.claude/plugins/cache/relay-local/relay/...`. If your install layout differs, adjust the path — the script behavior is what matters.

- [ ] **Step 3: Manual smoke test**

```bash
# Simulate a tool-error input:
echo '{"tool_name": "Bash", "result": {"error": "exit 1"}}' \
  | adapters/claude/hooks/post-tool-use.sh
cat ~/.relay-hook-state.json

# Simulate recovery:
echo '{"tool_name": "Bash", "result": {"ok": true}}' \
  | adapters/claude/hooks/post-tool-use.sh
cat ~/.relay-hook-state.json
```

Expected: after the error, `errors_recent=1, last_status=error, suggest_capture=false`. After recovery, `errors_recent=0, last_status=ok, suggest_capture=true`.

- [ ] **Step 4: Commit**

```bash
git add adapters/claude/hooks/ adapters/claude/hooks.json
git commit -m "feat(adapter/claude): best-effort error-recovery detection hook"
```

---

## Task 5: Deploy update to RDS + App Runner

**Files:**
- Modify: `deploy/02-rds-init.sh` (also apply 002)

- [ ] **Step 1: Update `deploy/02-rds-init.sh`**

After the existing `psql -f central_api/sql/001_init.sql` line, add:

```bash
echo "[1b/2] Apply 002_reviews_trigger.sql"
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" \
  -v ON_ERROR_STOP=1 \
  -f central_api/sql/002_reviews_trigger.sql
```

- [ ] **Step 2: Apply to running RDS**

```bash
./deploy/02-rds-init.sh
```

Expected: both SQL files run. `\df relay_apply_review` shows the function.

- [ ] **Step 3: Rebuild + redeploy the API image**

```bash
./deploy/05-image-push.sh
aws apprunner start-deployment \
  --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
  --profile relay --region ap-northeast-2
```

Wait until status RUNNING (~5 min).

- [ ] **Step 4: Smoke test reviews endpoint against cloud URL**

```bash
URL=$(jq -r .apprunner_service_url .aws/deployment-state.json)

# seed a skill
SID=$(curl -sf -X POST "$URL/skills" \
  -H 'Content-Type: application/json' \
  -H 'X-Relay-Agent-Id: smoke-agent' \
  -d '{
    "name":"review-smoke","description":"d","when_to_use":"w","body":"b",
    "metadata":{"problem":{"symptom":"x"},"solution":{"approach":"y","tools_used":[]},
      "attempts":[],"context":{"languages":[],"libraries":[]}}
  }' | jq -r .id)
echo "seeded: $SID"

# review it
curl -sf -X POST "$URL/skills/$SID/reviews" \
  -H 'Content-Type: application/json' \
  -H 'X-Relay-Agent-Id: smoke-agent' \
  -d '{"signal":"good"}' | jq .

# confirm confidence updated
curl -sf "$URL/skills/$SID" -H 'X-Relay-Agent-Id: smoke-agent' | jq '{id, confidence, good_count, bad_count}'
```

Expected: `confidence=0.75, good_count=1, bad_count=0`.

- [ ] **Step 5: Commit**

```bash
git add deploy/02-rds-init.sh
git commit -m "chore(deploy): also apply 002_reviews_trigger.sql in RDS init"
```

---

## Exit Criteria for Week 3

1. `pytest` passes `90 + 3 = 93` tests (6 new review API tests + 3 new client-side review tests) + 1 skipped.
2. Live cloud smoke: `POST /skills/{id}/reviews` with `signal=good` updates `good_count=1`, `confidence=0.75`.
3. Three `signal=stale` reviews on a skill flip `status=stale` and exclude it from `/skills/search`.
4. Invalid signals (`bogus`) return 422.
5. Local MCP server registers `skill_review` alongside capture/list_local/upload/fetch (5 tools total).
6. Claude Code SKILL.md documents when to call `skill_review`.
7. `adapters/claude/hooks.json` + `post-tool-use.sh` exist and pass the manual smoke test.
8. `deploy/02-rds-init.sh` applies both 001 and 002 SQL.

---

## Explicit follow-ups (not Week 3)

1. **Stricter reason taxonomy.** Right now `reason` is free-form. SPEC §4.5 lists a fixed enum; we'll enforce that once UX patterns stabilize.
2. **Review de-duplication.** An agent can currently review the same skill multiple times. Add a unique constraint on `(skill_id, agent_id)` when we know whether re-reviews should overwrite or reject.
3. **Hook → auto `skill_capture`.** Current hook only flags suggestions. Wiring to actually invoke `skill_capture` requires a matching `UserPromptSubmit`/`Notification` hook that reads the state file and calls the MCP tool — more plumbing than fits this week.
4. **Usage log insertion from search/fetch.** SPEC §4.4 mentions a "viewed" `usage_log` entry on fetch. Not implemented in Week 2; keep deferred.

---

## Self-review — performed

- **Spec coverage.** SPEC §4.5 `skill_review` (Task 1–2). SPEC §5 `POST /skills/{id}/reviews` (Task 1). SPEC §8 Week 3 "review 루프 + auto-capture" covered by Tasks 0–4. Stale auto-transition at ≥3 stale reviews is the SPEC threshold.
- **Placeholder scan.** No TBD / similar-to / generic "handle errors". Every SQL, Python, and shell block is runnable.
- **Type consistency.** `ReviewSignal` Literal matches the DB CHECK constraint (`good|bad|stale`). `ReviewRequest` / `ReviewResponse` mirror the ORM columns. `Signal` type in `review.py` matches `ReviewSignal` (duplicated intentionally: server and client types are independent surfaces; they happen to coincide for MVP).
- **Determinism.** The confidence formula is exactly `(good + 0.5) / GREATEST(good + bad + 1, 1)` in both the tests and the SQL trigger — tests assert 0.75 for (1,0,1) and 0.25 for (0,1,1).

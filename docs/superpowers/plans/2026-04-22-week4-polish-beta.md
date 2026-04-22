# Relay Week 4 — Polish + Closed Beta

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take Relay from "works end-to-end for one developer" to "five invited beta users can install, use, and provide feedback without hand-holding." Ship a one-line installer, a coherent set of slash commands, a QUICKSTART doc, an onboarding pack (plus a feedback channel), and a first live-dogfood metric pass.

**Architecture:** Three parallel threads, each independent enough for separate implementer dispatches.

1. **Install UX** — `install.sh` single-command setup (check prereqs → clone → venv → `pip install` → symlink `relay-mcp` → `claude plugin install relay@relay-local`). Plus `make reset-local` for wiping local skills during testing.
2. **Slash commands + prompts** — a coherent `/relay:*` set that wraps the five MCP tools, with tight Claude-facing instructions. Renaming `relay:relay-capture` → `relay:capture` is a known ugly-path that needs fixing.
3. **Beta pack + metrics** — a 1-page QUICKSTART, a `feedback.md` template skill, a daily metrics script that summarizes uses / hit rate / new captures. Not trying to be a full dashboard — just "can I tell if the dogfood is working after 2 weeks."

**Tech Stack:** pure shell + markdown. Nothing new to install. AWS stack unchanged. No new FastAPI endpoints.

---

## File Structure

```
relay/
├── install.sh                                  # NEW: one-line installer for new users
├── Makefile                                    # NEW: reset-local, test, up, down convenience targets
├── QUICKSTART.md                               # NEW: 3-minute "what do I do?" doc
├── BETA.md                                     # NEW: 5-user onboarding + feedback protocol
│
├── adapters/claude/
│   ├── .claude-plugin/plugin.json              # MODIFY: bump version
│   ├── SKILL.md                                # MODIFY: tighten per-tool guidance, add "search first" reminder
│   └── commands/
│       ├── relay-capture.md                    # MODIFY: rename logical slash to /relay:capture (file stays)
│       ├── relay-search.md                     # NEW: /relay:search <query> wrapper
│       ├── relay-upload.md                     # NEW: /relay:upload <name> — confirm + upload
│       ├── relay-review.md                     # NEW: /relay:review <skill_id> <good|bad|stale>
│       └── relay-status.md                     # NEW: /relay:status — list-local + drift summary
│
├── scripts/
│   ├── metrics.py                              # NEW: pull uses/captures/confidence stats from RDS
│   └── reset-local.sh                          # NEW: wipe ~/.claude/skills/{mine,downloaded,staging}
│
├── docs/
│   ├── BETA_INVITE_TEMPLATE.md                 # NEW: what to paste into DMs for 5 beta users
│   └── verification/
│       └── week4-beta-smoke.md                 # NEW: captures each beta user's first-hour experience
│
└── central_api/
    └── (unchanged)
```

---

## Task 0: Installer script

**Files:**
- Create: `install.sh`
- Create: `Makefile`

- [ ] **Step 1: Write `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Relay one-line installer.
# Usage: curl -fsSL https://raw.githubusercontent.com/treesoop/relay/main/install.sh | bash
# Or:    ./install.sh
#
# Installs the Relay MCP server locally and wires it into Claude Code via the
# bundled local marketplace. Idempotent — safe to re-run.

REPO_URL="${RELAY_REPO_URL:-https://github.com/treesoop/relay.git}"
INSTALL_DIR="${RELAY_INSTALL_DIR:-$HOME/.relay}"
BIN_DIR="${RELAY_BIN_DIR:-$HOME/.local/bin}"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
fail() { printf "\n\033[1;31merror:\033[0m %s\n" "$*" >&2; exit 1; }

# --- preflight ---
command -v git      >/dev/null || fail "git is required"
command -v python3  >/dev/null || fail "python3 is required"
command -v claude   >/dev/null || fail "Claude Code CLI is required (https://claude.com/claude-code)"

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
case "$PY_VER" in
  3.11|3.12|3.13|3.14) ;;
  *) fail "Python 3.11+ required (found $PY_VER)" ;;
esac

# --- clone or update ---
if [ -d "$INSTALL_DIR/.git" ]; then
  say "updating existing install at $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  say "cloning $REPO_URL -> $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- venv + editable install ---
say "setting up virtualenv"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet

# --- symlink relay-mcp onto PATH ---
mkdir -p "$BIN_DIR"
ln -sfn "$INSTALL_DIR/.venv/bin/relay-mcp" "$BIN_DIR/relay-mcp"

case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) say "warning: $BIN_DIR is not on PATH; add it to your shell profile"; ;;
esac

# --- claude plugin ---
if claude plugin list 2>/dev/null | grep -q '^  ❯ relay@'; then
  say "relay plugin already installed"
else
  say "registering local marketplace"
  claude plugin marketplace add "$INSTALL_DIR" || true
  say "installing relay plugin"
  claude plugin install relay@relay-local
fi

say "done."
cat <<EOF

Next:
  1) Restart Claude Code so the MCP server picks up.
  2) Try /relay:status in any session.
  3) See $INSTALL_DIR/QUICKSTART.md for the 3-minute walkthrough.
EOF
```

Make it executable: `chmod +x install.sh`.

- [ ] **Step 2: Write `Makefile`**

```makefile
.PHONY: help install test up down reset-local deploy-redeploy smoke

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install deps in existing venv
	pip install -e ".[dev]"

test: ## Run the full test suite
	pytest -q

up: ## Start docker-compose (postgres + api)
	docker compose up -d
	@echo "api: http://localhost:8080"

down: ## Stop docker-compose
	docker compose down

reset-local: ## Wipe ~/.claude/skills/{mine,downloaded,staging}
	./scripts/reset-local.sh

deploy-redeploy: ## Rebuild image + trigger App Runner deploy
	./deploy/05-image-push.sh
	aws apprunner start-deployment \
	  --service-arn "$$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
	  --profile relay --region ap-northeast-1

smoke: ## Run cloud smoke tests against live App Runner
	./deploy/08-smoke.sh
	./deploy/09-reviews-smoke.sh
```

- [ ] **Step 3: Commit**

```bash
chmod +x install.sh
git add install.sh Makefile
git commit -m "feat(install): one-line installer + Makefile convenience targets"
```

---

## Task 1: Reset-local + metrics scripts

**Files:**
- Create: `scripts/reset-local.sh`
- Create: `scripts/metrics.py`

- [ ] **Step 1: Write `scripts/reset-local.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${RELAY_SKILL_ROOT:-$HOME/.claude/skills}"

read -rp "Delete ALL skills under $ROOT/{mine,downloaded,staging}? [y/N] " REPLY
[ "${REPLY,,}" = "y" ] || { echo "aborted."; exit 1; }

for sub in mine downloaded staging; do
  [ -d "$ROOT/$sub" ] && { rm -rf "$ROOT/$sub"; echo "  wiped $sub/"; }
done

echo "done."
```

`chmod +x scripts/reset-local.sh`.

- [ ] **Step 2: Write `scripts/metrics.py`**

```python
"""Nightly metrics dump for Relay central API.

Usage:
    source .venv/bin/activate
    python scripts/metrics.py                # reads RELAY_DATABASE_URL
    python scripts/metrics.py --url "$URL"   # override

Prints: skill count, uploads-24h, reviews-24h, avg confidence, stale %,
top-5 most-used skills, bottom-5 lowest-confidence active skills.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


QUERIES = {
    "total_active": "SELECT COUNT(*) FROM skills WHERE status = 'active'",
    "total_stale": "SELECT COUNT(*) FROM skills WHERE status = 'stale'",
    "uploads_24h": "SELECT COUNT(*) FROM skills WHERE created_at > NOW() - INTERVAL '24 hours'",
    "reviews_24h": "SELECT COUNT(*) FROM reviews WHERE created_at > NOW() - INTERVAL '24 hours'",
    "avg_confidence": "SELECT ROUND(AVG(confidence)::numeric, 3) FROM skills WHERE status = 'active'",
    "top_used": """
        SELECT name, used_count, confidence
          FROM skills
         WHERE status = 'active'
         ORDER BY used_count DESC
         LIMIT 5
    """,
    "lowest_conf": """
        SELECT name, confidence, good_count, bad_count
          FROM skills
         WHERE status = 'active' AND (good_count + bad_count) >= 2
         ORDER BY confidence ASC
         LIMIT 5
    """,
}


async def run(url: str) -> int:
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            for name, q in QUERIES.items():
                result = await conn.execute(text(q))
                rows = result.fetchall()
                print(f"\n== {name} ==")
                for row in rows:
                    print("  " + " | ".join(str(x) for x in row))
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("RELAY_DATABASE_URL"))
    args = p.parse_args()
    if not args.url:
        print("error: --url or RELAY_DATABASE_URL required", file=sys.stderr)
        return 2
    return asyncio.run(run(args.url))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke-test `metrics.py` against RDS**

```bash
source .venv/bin/activate
RELAY_DATABASE_URL=$(jq -r --arg u "$(jq -r .db_user .aws/deployment-state.json)" \
                           --arg p "$(jq -r .db_password .aws/deployment-state.json)" \
                           --arg h "$(jq -r .db_endpoint .aws/deployment-state.json)" \
                           --arg d "$(jq -r .db_name .aws/deployment-state.json)" \
                           -n '"postgresql+asyncpg://\($u):\($p)@\($h):5432/\($d)"' \
                  .aws/deployment-state.json)
python scripts/metrics.py
```

Expected: prints 7 blocks (total_active, total_stale, uploads_24h, reviews_24h, avg_confidence, top_used, lowest_conf). Given the current skill corpus this should show ~4-6 active skills with a handful of reviews.

- [ ] **Step 4: Commit**

```bash
chmod +x scripts/reset-local.sh
git add scripts/reset-local.sh scripts/metrics.py
git commit -m "feat(scripts): reset-local helper + nightly metrics dump"
```

---

## Task 2: Slash commands for all 5 MCP tools

**Files:**
- Modify: `adapters/claude/.claude-plugin/plugin.json` (bump version to 0.2.0)
- Rename logically: file `commands/relay-capture.md` still `/relay:capture` but we fix the current quirk
- Create: `adapters/claude/commands/relay-status.md`
- Create: `adapters/claude/commands/relay-search.md`
- Create: `adapters/claude/commands/relay-upload.md`
- Create: `adapters/claude/commands/relay-review.md`
- Modify: `adapters/claude/SKILL.md` (tighten per-tool guidance)

**Scope note on naming:** Claude Code constructs the slash command from `plugin_name:command_filename`. Our plugin is named `relay` and the file is `relay-capture.md`, which yields `/relay:relay-capture` — ugly. Renaming `relay-capture.md → capture.md` would give the clean `/relay:capture`. Do that rename during this task.

- [ ] **Step 1: Bump plugin version**

Edit `adapters/claude/.claude-plugin/plugin.json`:

```json
{
  "name": "relay",
  "version": "0.2.0",
  "description": "Relay — agent skill sharing (Week 4: full commons — capture, search, upload, fetch, review)",
  "mcpServers": {
    "relay": {
      "command": "relay-mcp",
      "args": []
    }
  }
}
```

- [ ] **Step 2: Rename + update `relay-capture.md` → `capture.md`**

```bash
cd /Users/dion/potenlab/our_project/relay
git mv adapters/claude/commands/relay-capture.md adapters/claude/commands/capture.md
```

Replace the contents of `adapters/claude/commands/capture.md`:

```markdown
---
name: relay:capture
description: Capture the current session as a Relay skill (Problem → Attempts → Solution)
---

You are about to call the `skill_capture` MCP tool.

Before calling:
1. Summarize the problem just solved in one sentence.
2. List every failed attempt with its failure reason. NEVER omit failures.
3. State what finally worked.
4. List the tools used: each as `{type: "mcp"|"library"|"cli", name: "..."}`.
5. Propose a kebab-case skill name.
6. Confirm with the user before writing.

Then call `skill_capture` with all required fields. Afterwards, show the user:
- The resulting `skill_md_path` and `relay_yaml_path`.
- A reminder that this is local-only; call `/relay:upload <name>` to share it.
```

- [ ] **Step 3: Create `commands/status.md` (`/relay:status`)**

```markdown
---
name: relay:status
description: Show a summary of locally stored Relay skills with drift flags
---

Call `skill_list_local`. Format the result as a short table with columns:

    name | id | location | uploaded | drift

Under the table, briefly highlight:
- Any skills with `drift_detected: true` (and suggest `/relay:upload` to re-sync).
- The count per location (mine vs downloaded vs staging).

Do not call any other MCP tool in this command.
```

- [ ] **Step 4: Create `commands/search.md` (`/relay:search`)**

```markdown
---
name: relay:search
description: Search the central Relay commons for skills matching a query
---

Ask the user for a search query if they did not include one after the command.

Resolve the API URL from:
- Environment variable `RELAY_API_URL`, if set.
- Otherwise the URL printed in the Relay README's "Live URL" section.

Agent id: use `RELAY_AGENT_ID` if set, else `local-dev`.

Call `skill_search` (use the MCP tool with `search_mode="problem"` by default, limit 5).
Note: if `skill_search` is not yet a registered MCP tool, fall back to running
`curl -s -G "$URL/skills/search" --data-urlencode "query=..."` via Bash.

Format results compactly:
- One line per hit: `name (sim=<x.xx>, conf=<x.xx>): <symptom>`
- If any result has `missing_tools`, list them in a warning line.

Do not auto-fetch skills; ask the user which one to fetch.
```

- [ ] **Step 5: Create `commands/upload.md` (`/relay:upload`)**

```markdown
---
name: relay:upload
description: Upload a local `mine/<name>` skill to the central Relay API
---

Parse the skill name from the user's arguments. If none, list locally-uploadable
skills via `skill_list_local` (filter to `location=mine` AND `uploaded=false`) and
ask which one to upload.

Resolve `api_url` + `agent_id` from env (see /relay:search) or defaults.

Before calling `skill_upload`:
- Show a short preview: name, description, problem.symptom.
- Warn the user that PII in the body and in `attempts[].failed_because` will be
  masked server-side and that the masked body is written back locally.
- Confirm.

Then call `skill_upload` and report the returned `remote_id`.
```

- [ ] **Step 6: Create `commands/review.md` (`/relay:review`)**

```markdown
---
name: relay:review
description: Submit a good/bad/stale review for a central Relay skill
---

Expected arguments: `<skill_id> <signal>` where signal ∈ {good, bad, stale}.

If either arg is missing, ask the user. For `signal=bad`, also ask for a `reason`
(free text for MVP).

Resolve `api_url` + `agent_id` from env as in /relay:search.

Before calling `skill_review`:
- If the skill was fetched locally, read its metadata and show name + confidence.
- Confirm the signal + reason.

Call `skill_review` and report the returned `review_id`. Remind the user that
three `stale` reviews auto-flip the skill to `status=stale`.
```

- [ ] **Step 7: Tighten `SKILL.md`**

Replace the body of `adapters/claude/SKILL.md` (keep frontmatter) with:

```markdown
# Relay Agent Behavior

You have five MCP tools for the shared skill commons:

| Tool | When |
|---|---|
| `skill_search` | **ALWAYS try first** when starting a non-trivial task. Search by `problem` mode with a natural-language description of your situation. |
| `skill_fetch` | After picking a search result. Use `mode=staging` for previews, `mode=downloaded` once you're committing to try it. |
| `skill_capture` | After recovering from non-trivial errors OR when the user says save this / remember this. Local-only until uploaded. |
| `skill_upload` | When the user confirms they want a captured skill shared with the commons. Masks PII, rewrites the local body with the masked version. |
| `skill_review` | After USING a fetched skill. One honest signal per use — `good`, `bad`, or `stale`. |

## When to search

Before starting a difficult task, ask: "have I seen this before?" Call `skill_search`
with a natural-language description of the symptom. If similarity > 0.7 and
confidence > 0.5 on the top hit, read it before you start.

## When to capture

After you solve something through trial and error:
1. Enumerate the attempts and their failure reasons. Never omit a failed attempt.
2. Propose a kebab-case name.
3. Confirm with the user before calling `skill_capture`.
4. Ask whether they want to share it via `skill_upload`.

## When to review

Always call `skill_review` after you used a fetched skill. One review per use.

## When NOT to call these tools

- For trivial fixes that don't require creative problem-solving.
- Without explicit user consent for `skill_upload`.
- To inflate counts: one honest review per use.
```

- [ ] **Step 8: Verify slash commands in live Claude Code (manual)**

Re-install the plugin (or wait until the user restarts):

```bash
claude plugin marketplace update relay-local
claude plugin install relay@relay-local
```

Then in a fresh Claude Code session, confirm `/relay:capture`, `/relay:status`, `/relay:search`, `/relay:upload`, `/relay:review` all show up in the slash command menu.

Document any surprises in `docs/verification/week4-beta-smoke.md`.

- [ ] **Step 9: Commit**

```bash
git add adapters/claude/
git commit -m "feat(adapter/claude): full /relay:* slash command set + tightened SKILL.md"
```

---

## Task 3: QUICKSTART + BETA docs

**Files:**
- Create: `QUICKSTART.md`
- Create: `BETA.md`
- Create: `docs/BETA_INVITE_TEMPLATE.md`
- Create: `docs/verification/week4-beta-smoke.md` (stub)

- [ ] **Step 1: Write `QUICKSTART.md`**

```markdown
# Relay Quickstart

3 minutes to first capture + share.

## Prerequisites

- Claude Code installed (see https://claude.com/claude-code)
- Python 3.11+
- git

## Install

    curl -fsSL https://raw.githubusercontent.com/treesoop/relay/main/install.sh | bash

Or clone and run locally:

    git clone https://github.com/treesoop/relay.git
    cd relay && ./install.sh

Restart Claude Code. You should see `plugin:relay:relay` in `/mcp` output.

## Your first skill

Talk to Claude Code about anything you're currently debugging. When you solve it,
say:

> "Capture this as a Relay skill."

Claude will call `/relay:capture` for you, proposing a name. Confirm it, and
the skill lands under `~/.claude/skills/mine/<name>/`.

Run `/relay:status` to see it listed.

## Sharing it

    /relay:upload <name>

This masks PII, POSTs the skill to the central commons, and updates the local
sidecar with the canonical server id.

## Discovering other people's skills

    /relay:search <natural language description of your problem>

Read the top results. If one matches, use `/relay:upload` to pull it into
`~/.claude/skills/downloaded/`.

After trying it:

    /relay:review <skill_id> good   # or bad / stale

## What gets uploaded

- The SKILL.md body (markdown prose)
- The `.relay.yaml` metadata (problem, attempts, solution, tools)

Bodies and failure messages are regex-masked for API keys, emails, and bearer
tokens before storage. Review the masked result before confirming.

## What stays local

- Anything you capture but don't `upload`.
- Private skill corpus under `~/.claude/skills/mine/`.

## Troubleshooting

- **`/mcp` shows no `plugin:relay:relay`** — restart Claude Code after install.
- **"relay-mcp: command not found"** — add `~/.local/bin` to your PATH.
- **Upload returns 500** — central API likely restarting; retry in 30s.
```

- [ ] **Step 2: Write `BETA.md`**

```markdown
# Relay Closed Beta Protocol

5-user dogfood for 2 weeks. Goal: figure out if the semi-automatic skill-sharing
loop actually changes how people use Claude Code.

## Invite list (target)

1-5 Korean AI community devs who use Claude Code daily. Diverse domains:
payments, ops, backend, frontend. Avoid: people who haven't used Claude Code in
the last 7 days.

## What beta users do

1. Install: `curl ... | bash`
2. Use Claude Code normally for 2 weeks.
3. When they solve something messy, run `/relay:capture`.
4. Before starting a non-trivial task, run `/relay:search` first.
5. After using any fetched skill, run `/relay:review <id> <good|bad|stale>`.

## What we measure (daily via `scripts/metrics.py`)

- Skills captured / skills uploaded
- Searches per day / median results per search
- Reviews per day, good-vs-bad-vs-stale ratio
- Skills auto-staled
- Avg confidence of active skills

## What we ask beta users (weekly)

- Did `/relay:search` return anything you actually used?
- Did you capture a skill you might otherwise have re-debugged?
- Anything broken / confusing / slow?

## Exit criteria (after 2 weeks)

GO to v1 if:
- 3+ users captured at least 3 skills each.
- At least 5 total `good` reviews across users.
- Search hit rate (top-1 confidence > 0.5) ≥ 30% when corpus has 20+ skills.

NO-GO if:
- Users stopped capturing after week 1.
- No cross-user fetches occurred (people only captured their own, never searched
  anyone else's).
- Infrastructure breaks more than twice.
```

- [ ] **Step 3: Write `docs/BETA_INVITE_TEMPLATE.md`**

```markdown
# Beta invite DM template

Adapt and send via DM. Keep it short — no one reads long pitches.

---

hi [name],

만든 게 있어서 테스트해볼 사람 찾는 중. 2주만.

Relay — Claude Code에서 방금 삽질한 문제를 skill로 저장해서 나중에
나도 쓰고 다른 사람도 쓰게 하는 commons 레이어.

설치:

    curl -fsSL https://raw.githubusercontent.com/treesoop/relay/main/install.sh | bash

매일 쓰다가 뭐 하나 해결할 때마다 /relay:capture 누르면 되고,
어려운 문제 시작할 때 /relay:search 먼저 해보면 됨.

2주 뒤 솔직한 피드백 주면 고마워.

READ:
- QUICKSTART: https://github.com/treesoop/relay/blob/main/QUICKSTART.md
- 전체 스펙: https://github.com/treesoop/relay/blob/main/SPEC.md
```

- [ ] **Step 4: Stub the smoke doc**

Create `docs/verification/week4-beta-smoke.md`:

```markdown
# Week 4 — beta onboarding smoke test

One section per invited user. Fill in as they come online.

## Template

```
### <user handle>
- Date: YYYY-MM-DD
- OS: macOS / Linux
- Install result: ok / failed (what failed)
- First /relay:capture: ok / failed
- First /relay:search: ok / failed
- First hour observations: <free text>
- Follow-up needed: yes / no
```

## Users

(none yet)
```

- [ ] **Step 5: Commit**

```bash
git add QUICKSTART.md BETA.md docs/BETA_INVITE_TEMPLATE.md docs/verification/week4-beta-smoke.md
git commit -m "docs(beta): Quickstart + BETA protocol + invite template + smoke stub"
```

---

## Task 4: Full local verification sweep

**Files:** no new files; this is a check-in task.

- [ ] **Step 1: Run full suite + confirm cloud reach**

```bash
cd /Users/dion/potenlab/our_project/relay
source .venv/bin/activate
pytest -q
URL=$(jq -r .apprunner_service_url .aws/deployment-state.json)
curl -sf "$URL/health" | jq .
python scripts/metrics.py 2>/dev/null | head -40 || echo "metrics script unreachable — expected if RDS creds not exported"
```

Expected: `93 passed, 1 skipped` (Week 1–3 baseline), health endpoint returns `{"status":"ok"}`.

- [ ] **Step 2: Install from scratch in a scratch directory**

```bash
TMP=$(mktemp -d)
cd "$TMP"
RELAY_INSTALL_DIR="$TMP/relay-test" RELAY_BIN_DIR="$TMP/bin" \
  bash /Users/dion/potenlab/our_project/relay/install.sh
PATH="$TMP/bin:$PATH" relay-mcp --help 2>&1 | head -3 || true   # stdio server — "no --help" is fine
rm -rf "$TMP"
```

If `install.sh` exits 0 and `relay-mcp` is resolvable on PATH, pass.

- [ ] **Step 3: Commit verification results**

Append to `docs/verification/week4-beta-smoke.md` under a new header "Week 4 Task 4 local install sweep" — paste the script output (trimmed).

```bash
git add docs/verification/week4-beta-smoke.md
git commit -m "docs(verification): Week 4 local install sweep"
```

---

## Exit Criteria for Week 4

1. `./install.sh` on a clean checkout completes in under 2 minutes and prints the restart instruction.
2. `make test` / `make up` / `make down` / `make reset-local` / `make smoke` all work.
3. `/relay:capture`, `/relay:status`, `/relay:search`, `/relay:upload`, `/relay:review` all show up and behave per their prompts.
4. `scripts/metrics.py` prints a populated report against RDS.
5. QUICKSTART + BETA + invite template exist, reviewed for typos.
6. `git log --oneline | head -5` shows Week 4 commits on `main`.

Beta onboarding of 5 users is OUT OF SCOPE for this implementation plan — that's the operational phase that follows.

---

## Self-review — performed

- **Spec coverage.** SPEC §8 Week 4 roadmap: install script (Task 0), slash commands (Task 2), documentation (Task 3), beta onboarding prep (Task 3), metrics (Task 1). Nothing new in the server — all features already shipped in Weeks 2/2B/2C/3.
- **Placeholder scan.** No "TBD"/"add error handling". Every script and doc is complete.
- **Type consistency.** Slash commands reference the existing MCP tool names (`skill_capture`, `skill_list_local`, `skill_upload`, `skill_fetch`, `skill_review`) — matches `local_mcp/server.py`.
- **Scope discipline.** No new Python modules, no new API endpoints, no schema changes. This is polish + documentation.

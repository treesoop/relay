<div align="center">

# Relay

**Your agent learned it once. Every agent on your team should know it.**

Relay is the institutional memory layer for coding agents — a shared
commons where Claude Code sessions write down what they figured out, so
the next session (yours or a teammate's) starts from the answer instead
of from zero.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2)](https://modelcontextprotocol.io)
[![Status](https://img.shields.io/badge/status-shipping-brightgreen.svg)](#roadmap)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-orange.svg)](https://www.anthropic.com/claude-code)
[![Dashboard](https://img.shields.io/badge/dashboard-live-c2410c.svg)](https://relay-dashboard-one.vercel.app)

</div>

---

## The 30-second pitch

```
> /relay:search aws app runner deploy seoul region

  apprunner-seoul-unsupported-use-tokyo   sim=0.86  conf=0.83
    App Runner is not available in ap-northeast-2 (Seoul) as of 2026.
    Use ap-northeast-1 (Tokyo) + cross-region ECR pull. No replication.

  Apply this? (fetch / just answer / skip)
```

Your agent just spent three hours learning that AWS App Runner doesn't
exist in Seoul. Without Relay, that lesson dies with the session —
tomorrow your teammate's agent rediscovers the same wall. With Relay, it
gets captured, shared, reviewed, and auto-activated in every future
session across your team.

---

## The problem we're solving

AI coding agents are constantly discovering things — that this library's
API changed, that this region doesn't support that service, that this
error is actually a typo three files away. Today that knowledge has no
good home:

| Where knowledge goes today | Why it's insufficient |
|---|---|
| **Per-session memory** (Claude memory, Cursor rules) | Personal. Invisible to your teammates. |
| **Public skill marketplaces** (official Claude skills, MCP registries) | Needs polished, curated submissions. Nothing captures the messy in-progress lesson from yesterday. |
| **Team docs** (Notion, Confluence, READMEs) | Human-authored. Agents don't update them. They rot. |
| **Chat history** | Not searchable across sessions. Not structured. Gone once the context window closes. |

What's missing is an **institutional memory that agents write to
directly** — structured, searchable, and shared at team scope.

---

## What Relay gives you

- 🧠 **Capture in-session** — when the agent just solved something, `/relay:capture` structures it as *Problem → Attempts → Solution*. The **failure log is preserved** — which paths didn't work, and why. That's often more valuable than the final answer.
- 🔍 **Semantic search across the team** — pgvector similarity over 384-dim BGE embeddings. Returns full skill bodies inline, so you apply a match without even downloading it.
- 📥 **Auto-activation** — `/relay:fetch` drops the skill into `~/.claude/skills/<name>/` so Claude Code loads it automatically next session. No config, no shell sourcing.
- ⭐ **Reviews keep quality honest** — `good` / `bad` / `stale` signals recompute confidence server-side. Three stale reviews auto-retire a skill so the commons doesn't rot.
- ✏️ **Edit in place** — re-uploading the same skill updates it. Cryptographically enforced: only the original author can modify or delete.
- 🔒 **PII masking** — emails, API keys, secrets are redacted server-side before storage. The masked body is written back locally so drift detection stays honest.
- 📐 **Plays nice with Claude Code's native format** — `SKILL.md` stays pure standard Claude skill. All Relay metadata lives in a `.relay.yaml` sidecar.

---

## Install

```bash
claude plugin marketplace add treesoop/relay
claude plugin install relay@relay
```

Restart Claude Code. On the first `/relay:*` call, the plugin registers
a per-machine agent id with the central API and stores a secret at
`~/.config/relay/credentials.json`. No Python, no pip, no venv required
— the plugin ships as slash commands that call the API directly.

**Prefer to self-host?** See [Server development](#server-development)
and [`deploy/README.md`](./deploy/README.md).

---

## Commands

| | |
|---|---|
| `/relay:search <query>` | Search the commons. Returns top matches with full skill bodies inline. |
| `/relay:fetch <id>` | Download a skill and wire it into auto-activation for next session. |
| `/relay:capture` | Save a new skill locally (Problem → Attempts → Solution). Stays local until you upload. |
| `/relay:upload <name>` | Push a local skill to the commons. Re-uploading edits in place. |
| `/relay:review <id> good\|bad\|stale [reason]` | Rate a skill after using it. |
| `/relay:status` | List every Relay-managed skill and flag drift between local edits and the server copy. |

---

## How it's different

| | Personal memory | Skill marketplace | **Relay** |
|---|---|---|---|
| Scope | one user | public | **your team** |
| Content | chat history | polished skills | **in-progress lessons, failures included** |
| Contribution | implicit | manual curation | **agent-written, in-session** |
| Search | recency-based | keyword browse | **semantic + confidence-weighted** |
| Quality | — | editorial review | **per-use reviews + auto-retire** |
| Audience | you | humans | **agents** |
| Edit-in-place | — | PR workflow | **author re-uploads, server PATCH** |

---

## Why the failure log matters

Every skill Relay captures is structured as:

> *"I tried X — failed because Y. Then I tried Z — worked because …"*

Most "how-to" content on the internet describes only the winning path.
But when an agent hits a similar problem, knowing **which paths to
skip** is often more valuable than the answer itself. Relay's
`/relay:capture` refuses to save a skill without the attempts list —
this is a deliberate design choice.

---

## On disk

```
~/.claude/skills/
├── mine/<name>/            captured locally
│   ├── SKILL.md            standard Claude Code format (frontmatter + body)
│   └── .relay.yaml         sidecar: problem, attempts, solution, id, drift hash
├── downloaded/<name>/      fetched from the commons
└── <name>                  flat symlink → Claude Code auto-activates from here
```

The filesystem is the source of truth locally — no SQLite, no daemon,
no local index. Drift between local edits and the server copy is
detected via SHA-256 over the skill body.

---

## Architecture

```
┌─ Claude Code ──────────────────────────┐
│  /relay:* slash commands               │
│       curl + jq over HTTPS             │
└──────────────┬─────────────────────────┘
               │
               ▼
┌─ Relay central API (FastAPI) ──────────┐
│  AWS App Runner · ap-northeast-1       │
│  ─ pgvector similarity search          │
│  ─ BGE-small-en-v1.5 embeddings (384d) │
│  ─ PII masking · confidence recompute  │
│  ─ agent-secret auth · author ACLs     │
└──────────────┬─────────────────────────┘
               │
               ▼
┌─ Postgres 16 + pgvector (RDS) ─────────┐
│  skills · reviews · usage_log · agents │
└────────────────────────────────────────┘
```

---

## Security

| | |
|---|---|
| Write auth | `X-Relay-Agent-Id` + `X-Relay-Agent-Secret`. Server stores only SHA-256 hash of the secret. |
| Ownership | `PATCH` and `DELETE` require `source_agent_id == caller` → non-owners get 403. |
| Rate limit | 100 requests/minute per agent. |
| Input caps | Body ≤ 50 KB, description ≤ 2 KB. |
| PII | Emails, API keys, tokens masked server-side before storage. |
| Embeddings | Local model (`BAAI/bge-small-en-v1.5`). No third-party API calls. OpenAI is an opt-in operator flag. |

---

## Roadmap

| | |
|---|---|
| ✅ Shipped | Six-command commons · agent-secret auth · author-scoped overwrite · symlink auto-activation · PII masking · reviews with confidence recompute · auto-stale after 3 stale signals · [web dashboard](https://relay-dashboard-one.vercel.app) on Vercel |
| 🚧 In progress | Adapters for Cursor / Gemini / Codex · public team dashboards |
| 🎯 Next | GitHub auto-deploy to App Runner · RDS moved behind VPC connector · team-scoped private commons |

---

## Server development

The `central_api/` tree holds the FastAPI service.

```bash
# Local dev (Postgres + API in docker-compose)
docker compose up -d

# Server tests
pip install -e ".[dev]"
RELAY_TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay \
  pytest central_api/tests                          # 61 tests

# Deploy to AWS
./deploy/05-image-push.sh
aws apprunner start-deployment \
  --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
  --profile relay --region ap-northeast-1
```

See [`deploy/README.md`](./deploy/README.md) for the full AWS runbook
(App Runner is amd64-only, not available in Seoul — use Tokyo with
cross-region ECR pull; this is also the first Relay skill in the
commons) and [`SPEC.md`](./SPEC.md) for the full data model.

---

## Who's this for

**Small teams running Claude Code who keep re-solving the same problems.**
If your teammates' agents keep rediscovering the same library quirks,
region gotchas, or debug paths — and the docs never get updated —
Relay is the layer that fixes it.

**Solo devs** get value too: your own past sessions become searchable
from every new session, across projects.

**Self-hosters** can run the whole stack (API + Postgres + pgvector)
from `docker compose up -d`. The server image is MIT-licensed.

---

## Contributing

Issues and PRs welcome. See [`SPEC.md`](./SPEC.md) for the architecture,
[`deploy/`](./deploy/) for the infrastructure scripts, and
[`docs/verification/`](./docs/verification/) for the end-to-end smoke
records.

---

<div align="center">

**Relay** — shared skill memory for coding agents.

[Install](#install) · [Commands](#commands) · [Architecture](#architecture) · [Roadmap](#roadmap) · [MIT License](./LICENSE)

</div>

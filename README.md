# Relay

**Shared skill memory for coding agents.**

Your agent just spent three hours figuring out that AWS App Runner
doesn't exist in Seoul. Tomorrow a teammate's agent will spend three
more figuring out the same thing. Relay is the layer that fixes this:
it captures what an agent learned — including the attempts that
failed — and makes it searchable from every other Claude Code
session on your team.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2)](https://modelcontextprotocol.io)

```
> /relay:search aws app runner deploy seoul region

  apprunner-seoul-unsupported-use-tokyo   sim=0.86  conf=0.83
    App Runner is not available in ap-northeast-2 (Seoul); use Tokyo
    (ap-northeast-1) + cross-region ECR pull. No replication needed.

  Apply this? (fetch / just answer / skip)
```

## The problem

AI coding agents solve hard problems every day and the work vanishes at
the end of the session. The next session — your own, or a teammate's —
starts from the same blank slate. There are tools around this, but none
of them cover the middle:

- **Per-session memory** (Claude memory, Cursor rules) is personal and
  invisible to the rest of your team.
- **Public skill marketplaces** need polished, curated submissions.
  Nothing captures the messy in-progress lesson from yesterday.
- **Shared docs** (Notion, wikis) are human-authored. Agents don't
  update them, and they rot.

What's missing is an **institutional memory layer that agents write into
directly** — one that captures not just the answer but the trail of
things that didn't work, and is instantly searchable the next time a
teammate hits the same wall.

## How Relay solves it

Relay is a commons: a central vector-searchable store that every
agent on your team reads from and writes to.

1. **Capture in-session.** When the agent solves something non-trivial,
   `/relay:capture` structures it as *Problem → Attempts → Solution*,
   with each failed attempt and its failure reason preserved. The
   failure log is often more useful than the final fix — it tells the
   next agent which paths *not* to take.

2. **Search before guessing.** `/relay:search <query>` runs a pgvector
   similarity search across the commons. The response includes full
   skill bodies inline, so the agent can read and apply a match without
   even downloading it.

3. **Fetch to auto-activate.** `/relay:fetch <id>` writes the skill to
   `~/.claude/skills/<name>/` so Claude Code's native skill loader picks
   it up automatically in every future session.

4. **Review to stay calibrated.** One `/relay:review good|bad|stale`
   after each use keeps confidence honest. Three stale signals
   auto-retire a skill so the commons doesn't rot.

5. **Edit in place.** Only the original author can modify or delete
   their own skill; re-uploading the same skill updates it instead of
   duplicating. Ownership is cryptographically enforced.

## Quickstart

```bash
claude plugin marketplace add treesoop/relay
claude plugin install relay@relay
```

Restart Claude Code. The first time you run any `/relay:*` command, the
plugin registers a per-machine agent id with the central API and stores
a secret at `~/.config/relay/credentials.json`.

## Commands

| | |
|---|---|
| `/relay:search <query>` | Search the commons. Returns top matches with full skill bodies inline. |
| `/relay:fetch <id>` | Download a skill and wire it into auto-activation for next session. |
| `/relay:capture` | Save a new skill locally (Problem → Attempts → Solution). Stays local until you upload. |
| `/relay:upload <name>` | Push a local skill to the commons. Re-uploading edits in place. |
| `/relay:review <id> good\|bad\|stale [reason]` | Rate a skill after using it. |
| `/relay:status` | List every Relay-managed skill and flag drift between local edits and the server copy. |

## How it's different

| | Personal memory | Skill marketplace | **Relay** |
|---|---|---|---|
| Scope | one user | public | **your team** |
| Content | chat history | polished skills | **in-progress lessons, including failures** |
| Contribution | implicit | manual curation | **agent-written, in-session** |
| Search | recency | keyword browse | **semantic + confidence** |
| Quality | — | editorial | **reviews + auto-retire** |
| Audience | you | humans | **agents** |

## On disk

Each skill is a two-file directory:

```
~/.claude/skills/
├── mine/<name>/            captured locally
│   ├── SKILL.md            standard Claude Code format (frontmatter + body)
│   └── .relay.yaml         sidecar: problem, attempts, solution, id, drift hash
├── downloaded/<name>/      fetched from the commons
└── <name>                  flat symlink — Claude Code auto-activates from here
```

The Relay metadata lives in the sidecar, never in the SKILL.md
frontmatter, so Claude Code's official schema stays untouched. The
filesystem is the source of truth locally — no SQLite, no daemon, no
local index. Drift detection is a SHA-256 over the body.

## Security + privacy

- Writes authenticated per agent: `X-Relay-Agent-Id` + `X-Relay-Agent-Secret`.
- `PATCH` and `DELETE` are author-scoped — only the original uploader can modify their skill. Non-owners get 403.
- 100 requests/minute per agent. Body ≤ 50 KB.
- PII (emails, API keys) masked server-side before storage. The masked body is written back to your local SKILL.md so drift detection stays honest.
- Embeddings run on the server with `BAAI/bge-small-en-v1.5`. No third-party API calls. OpenAI embeddings are an opt-in env flag for operators.

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

## Server development

The `central_api/` tree holds the service. Typical loop:

```bash
docker compose up -d                               # Postgres + API
pip install -e ".[dev]"                            # server deps
RELAY_TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay \
  pytest central_api/tests                          # 61 tests

./deploy/05-image-push.sh                          # push to ECR
aws apprunner start-deployment \
  --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
  --profile relay --region ap-northeast-1
```

See [`deploy/README.md`](./deploy/README.md) for the full AWS runbook
(App Runner is amd64-only and not available in Seoul — use Tokyo with
cross-region ECR pull) and [`SPEC.md`](./SPEC.md) for the data model.

## Roadmap

Shipped: the six-command commons, agent-secret auth, author-scoped
overwrite, symlink auto-activation, PII masking, reviews with
confidence recompute, auto-stale.

On deck: GitHub auto-deploy, RDS behind a VPC connector, web dashboard
for browsing the commons, adapters for Cursor / Gemini / Codex.

## License

[MIT](./LICENSE)

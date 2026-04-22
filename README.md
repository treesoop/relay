# Relay

**Agent skill sharing for Claude Code, Cursor, Gemini, and Codex.**
A local-first MCP server that captures what an agent learned and makes it discoverable to others.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2)](https://modelcontextprotocol.io)
[![Tests](https://img.shields.io/badge/tests-109%20passing-brightgreen.svg)](#development)

---

## What is Relay?

Relay is the missing middle layer between personal agent memory and public skill marketplaces.
Agents contribute what they learn, discover what others learned, and review what worked — automatically.

- **Captures** a problem-solving session as a structured skill (Problem → Attempts → Solution → Tools used → When NOT to use).
- **Stores** skills on the local filesystem as `SKILL.md` + `.relay.yaml` sidecar — native to Claude Code's skill loader, no custom formats.
- **Shares** them (Week 2+) via a central server with semantic search powered by pgvector and OpenAI embeddings.
- **Reviews** good/bad/stale to keep the commons healthy.

Unlike traditional memory systems that just store "what happened," Relay skills preserve the **failure path** — the approaches the agent tried and why they failed. Because the failure log is often more valuable than the winning attempt.

## Why Relay

| | Claude Memory | Skills Marketplaces | **Relay** |
|---|---|---|---|
| Scope | personal | public | personal → shared commons |
| Contribution | implicit | manual | **automatic / semi-automatic** |
| Content | chat history | polished skills | structured problem-solution records |
| Search | recent session | keyword browse | **semantic RAG + confidence** |
| Platforms | Claude | any | **Claude Code, Cursor, Gemini, Codex** |

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/treesoop/relay.git
cd relay
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Make the MCP binary discoverable
mkdir -p ~/.local/bin
ln -s "$(pwd)/.venv/bin/relay-mcp" ~/.local/bin/relay-mcp

# 3. Register the local marketplace and install the plugin
claude plugin marketplace add "$(pwd)"
claude plugin install relay@relay-local

# 4. Restart Claude Code. The MCP server shows as plugin:relay:relay - Connected
```

Then, inside a Claude Code session:

> "I just solved a Stripe 429 issue. First I tried a simple retry loop — got banned for 10 minutes. Then fixed 1s sleep — still rate-limited. Finally used exponential backoff with Retry-After header via tenacity. Save this as `stripe-rate-limit-handler`."

Claude calls `skill_capture` via MCP. The skill lands at `~/.claude/skills/mine/stripe-rate-limit-handler/` with a `SKILL.md` Claude Code auto-loads on next session.

## How it works

```
Claude Code / Cursor / Gemini / Codex
          |
          | MCP (stdio)
          v
  Local MCP Server (FastMCP, Python)
          |
          v
  ~/.claude/skills/
  |-- mine/<name>/          captured locally
  |   |-- SKILL.md          official Claude Code format
  |   `-- .relay.yaml       problem / attempts / solution metadata
  |-- downloaded/<name>/    fetched from the commons
  `-- <name>                flat symlink → mine/ or downloaded/
                            (Claude Code auto-activates from this path)
          |
          | HTTPS (Week 2+)
          v
  Central API (FastAPI on AWS App Runner)
  Postgres + pgvector on RDS
  Local embeddings — BGE-small-en-v1.5 (384 dims, sentence-transformers)
  OpenAI text-embedding-3-small — opt-in via env var
```

Each skill is a two-file directory:

- **`SKILL.md`** — the pure Claude Code skill the agent reads and follows.
- **`.relay.yaml`** — structured metadata (problem, attempts, solution, tools used, confidence, drift hash) for search, ranking, and integrity checks.

The split means Relay never breaks Claude Code's official skill schema — custom fields live in the sidecar, not in the frontmatter.

## What's in the box

- **MCP tools**: `skill_capture`, `skill_list_local`, `skill_upload`, `skill_fetch`, `skill_review` — with matching `/relay:*` Claude Code slash commands.
- **Central API** on AWS App Runner + RDS Postgres 16 with pgvector (384-dim). Hybrid ranking over similarity × confidence × context match.
- **Local embeddings** — `BAAI/bge-small-en-v1.5` via sentence-transformers. No API keys. OpenAI embeddings are a one-env-var opt-in.
- **Symlink auto-activation**. Every captured or fetched skill lands at `~/.claude/skills/<name>` so Claude Code picks it up on the next session without a custom hook.
- **Reviews + confidence**. Good/bad updates confidence; three stale signals auto-retire a skill.
- **Agent-secret auth** (see [Security](#security)). Writes require `X-Relay-Agent-Secret`; `PATCH` and `DELETE` are author-scoped so only the original uploader can mutate their skill.
- **Drift detection** via SHA-256 body hash, so local edits after upload are visible.
- **Rate limits + input caps**: 100 req/min per agent, body ≤ 50 KB, description ≤ 2 KB.
- **PII masking** of bodies and attempts before anything hits storage.
- **109 tests** — 48 local MCP + 61 central API.

## Privacy and embeddings

Relay runs a **local embedding model** (`BAAI/bge-small-en-v1.5`, 384 dims, MTEB avg 62.17) by default. Your skill bodies never leave the Relay server, and no OpenAI API key is required.

To opt in to OpenAI's embeddings (for possibly higher quality at some scale), set:

    RELAY_EMBEDDING_PROVIDER=openai
    RELAY_OPENAI_API_KEY=sk-...

This also requires the DB schema to use `vector(1536)` instead of `vector(384)`. See the migration recipe below.

### Changing embedding dimensions later

Skill bodies and metadata are the source of truth; embeddings are a derived cache. To migrate to a different model/dimension:

1. **For dev / small corpora:** edit `central_api/sql/001_init.sql` and `central_api/models.py`, then `docker compose down -v && docker compose up -d postgres`. Re-upload skills (only ever tens or hundreds).
2. **For production / existing corpora:**
   - Add new columns (`description_embedding_v2 vector(N)`, etc.) via migration.
   - Backfill by iterating every skill and calling the new embedder on its stored body + metadata.
   - Switch search/upload code to the `_v2` columns.
   - Drop the old columns and indexes once traffic is fully cut over.

Because `body` (TEXT) and `metadata` (JSONB) are always preserved, embedding migration is a pure recomputation — no data can be lost.

## Security

Writes to the commons (upload / overwrite / review / delete) are authenticated with a per-agent secret:

1. On the first upload, the client calls `POST /auth/register` and the server issues a secret **once**. It's persisted locally at `~/.config/relay/credentials.json` (mode 0600) — the server only keeps its SHA-256 hash.
2. Every write request must carry `X-Relay-Agent-Id` + `X-Relay-Agent-Secret`. A wrong secret returns 401.
3. `PATCH` and `DELETE` on a skill additionally require `source_agent_id == authenticated agent`, so only the original uploader can modify or remove their own skills.
4. Read endpoints (`GET /skills`, `GET /skills/search`, `GET /skills/{id}`) only need `X-Relay-Agent-Id` — the commons is public-read for now.
5. Input size caps: description ≤ 2 KB, body ≤ 50 KB. Rate limit: 100 requests/minute per agent.

Legacy agents created before auth shipped get a fresh secret on their next `POST /auth/register` call (server-side migration path; no manual reset needed).

## Deployment

Relay's central API ships to AWS App Runner (Seoul, `ap-northeast-2`) with RDS PostgreSQL 16 + pgvector. All infrastructure lives in `deploy/` as idempotent shell scripts — no Terraform yet, but each script writes its state to `.aws/deployment-state.json` so later steps and redeploys pick up existing ARNs.

### First-time provision

    ./deploy/00-preflight.sh
    ./deploy/01-rds-create.sh        # ~8 min wait
    ./deploy/02-rds-init.sh
    ./deploy/03-secrets-create.sh
    ./deploy/04-ecr-create.sh
    ./deploy/05-image-push.sh        # ~10-20 min first time (QEMU amd64)
    ./deploy/06-iam-create.sh
    ./deploy/07-apprunner-create.sh  # ~5-7 min wait
    ./deploy/08-smoke.sh

### Redeploy after a code change

    ./deploy/05-image-push.sh
    aws apprunner start-deployment \
      --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
      --profile relay --region ap-northeast-2

### Teardown

    ./deploy/99-teardown.sh          # irreversible after Secrets recovery window; confirms first

See `deploy/README.md` for the full runbook and known constraints (App Runner x86_64-only, public RDS, QEMU emulation on arm64 hosts).

## Roadmap

Shipped:

- Local MCP server, file-based skill storage, drift detection, capture/list tools.
- Central API — FastAPI on AWS App Runner, RDS Postgres + pgvector, local BGE embeddings, upload/fetch.
- Reviews, confidence recompute, auto-stale after three stale signals.
- Installer + slash commands + symlink auto-activation, agent-secret auth, author-scoped `PATCH` / `DELETE`, rate limits, input caps.

On deck:

- GitHub auto-deploy wired into the ECR → App Runner pipeline.
- RDS moved behind a VPC connector.
- Web dashboard for browsing the commons.
- Cross-client adapters (Cursor, Gemini, Codex).

Full design in [`SPEC.md`](./SPEC.md). Week-by-week plans in [`docs/superpowers/plans/`](./docs/superpowers/plans/).

## Design principles

1. **File-first, DB-never on the client.** The filesystem is the source of truth for local skills. No SQLite, no local index — Claude Code's native skill discovery already does the heavy lifting.
2. **Claude Code official format is sacred.** Relay metadata never pollutes SKILL.md frontmatter. All extensions live in `.relay.yaml` sidecars.
3. **Structured problem records, not polished essays.** Skills capture Problem → Attempts → Solution, including the failure log. The failure log is often more valuable than the answer.
4. **MCP is the cross-platform contract.** The core 6 MCP tools work on any MCP-supporting client. Platform-specific auto-triggers (e.g. Claude Code hooks) are thin adapters.
5. **Human-in-the-loop before anything hits the commons.** Captures are local-only by default. Upload is a separate, explicit step.

## Development

Requires Python 3.11+.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Local MCP tests (no services required)
pytest tests/                                   # 48 tests

# Full suite including central API (needs postgres + pgvector)
docker compose up -d postgres
RELAY_TEST_DATABASE_URL="postgresql+asyncpg://relay:relay@localhost:5432/relay" \
  pytest                                        # 109 tests
```

Layout:

```
local_mcp/          local MCP server (tools, types, fs, drift)
adapters/claude/    Claude Code plugin (.claude-plugin/, SKILL.md, commands/)
docs/               spec, plans, live verification records
tests/              pytest suite — types, fs, drift, capture, list_local, server
```

See [`SPEC.md`](./SPEC.md) for the full architecture, data model, MCP tool contracts, and deployment plan.

## License

[MIT](./LICENSE)

## Related

- [Model Context Protocol](https://modelcontextprotocol.io) — the open standard Relay speaks.
- [Claude Code](https://www.anthropic.com/claude-code) — Anthropic's CLI; Relay's first-class integration target.
- [FastMCP](https://github.com/jlowin/fastmcp) — the Python MCP server framework powering the local side.
- [Anthropic Skills](https://docs.claude.com/en/docs/claude-code/skills) — the official skill format Relay extends.

---

Feedback and ideas welcome via GitHub issues.

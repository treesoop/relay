# Relay

**Agent skill sharing for Claude Code, Cursor, Gemini, and Codex.**
A local-first MCP server that captures what an agent learned and makes it discoverable to others.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/protocol-MCP-8A2BE2)](https://modelcontextprotocol.io)
[![Status: pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#roadmap)
[![Tests](https://img.shields.io/badge/tests-35%20passing-brightgreen.svg)](#development)

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
  |-- downloaded/           fetched from the commons (Week 2+)
  `-- staging/              search-result previews
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

## Current status — Week 1 shipped

**Local MCP server is live.** What works today:

- 6 typed domain classes (Attempt, ToolUsed, Problem, Solution, RelayMetadata) with YAML roundtrip.
- Filesystem layout under `~/.claude/skills/{mine,downloaded,staging}/` with path-traversal guards and kebab-case name validation.
- `write_skill` / `read_skill` with sidecar roundtrip.
- Drift detection via SHA-256 body hash (detects manual edits after a skill was uploaded).
- `skill_capture` MCP tool — structured input, no LLM call inside (the calling agent already interpreted the session).
- `skill_list_local` MCP tool — enumerates all Relay skills, flags drift.
- FastMCP stdio server, Claude Code plugin adapter (plugin manifest + SKILL.md + slash command).

**35 tests passing. 13 focused commits. Live end-to-end smoke test passed in Claude Code 2.1.116.**

## Week 2 shipped — central API + local embeddings

- FastAPI server with Postgres + pgvector (384-dim).
- Local BGE-small-en-v1.5 embeddings via sentence-transformers — no API keys required.
- `POST /skills`, `GET /skills/{id}`, `GET /skills/search` with hybrid ranking (similarity + confidence + context match).
- `skill_upload` + `skill_fetch` MCP tools, end-to-end tested through docker-compose.
- PII masking of bodies and attempts before storage.
- OpenAI embeddings available behind a single env var flip.

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

## Roadmap

Relay is a 4-week MVP targeting dogfood release.

- **Week 1 — Local MCP + file storage** · *done*
- **Week 2 — Central API** · FastAPI on AWS App Runner (Seoul region), RDS Postgres + pgvector, OpenAI embeddings, `skill_upload` / `skill_fetch`.
- **Week 3 — Review + auto-capture** · `skill_review`, confidence re-scoring, stale auto-transition, error-recovery hook.
- **Week 4 — Polish + closed beta** · install script, slash commands, documentation, 5-user closed beta.

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
pytest           # 35 tests, should all pass
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

Built as a dogfood experiment. Feedback and ideas welcome via GitHub issues.

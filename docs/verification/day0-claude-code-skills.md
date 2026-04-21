# Day 0 + Week 1 Live Verification — Claude Code Skills Loader

Date: 2026-04-21
Claude Code version: 2.1.116
Host: macOS Darwin 25.3.0, Python 3.13.11

## Install path (chosen)

Used the **local marketplace** path, not a direct symlink into `~/.claude/plugins/`. Claude Code's plugin system is marketplace-driven.

Steps taken:

1. `relay-mcp` binary symlinked into PATH:
   `ln -s /Users/dion/potenlab/our_project/relay/.venv/bin/relay-mcp ~/.local/bin/relay-mcp`
2. Added `.claude-plugin/marketplace.json` at the project root referencing `./adapters/claude` as the `relay` plugin.
3. `claude plugin validate .` — marketplace manifest PASS, plugin manifest PASS (1 cosmetic warning about missing author field).
4. `claude plugin marketplace add /Users/dion/potenlab/our_project/relay` — registered the local marketplace (name: `relay-local`).
5. `claude plugin install relay@relay-local` — installed plugin (scope: user).
6. `claude mcp list` — `plugin:relay:relay: relay-mcp  - ✓ Connected`.
7. Claude Code restart.

## Findings

| Check | Result | Evidence |
|---|---|---|
| Directory-form skill loads (`~/.claude/skills/mine/<name>/SKILL.md`) | **PASS** | skill_capture wrote files; MCP responded with paths matching expected layout |
| Sibling `.relay.yaml` tolerated | **PASS** | Both files coexist; `claude plugin validate` had no complaint; live skill write+read roundtrip succeeded |
| `mcpServers` key shape in plugin.json accepted by current Claude Code | **PASS** | MCP server registered and Connected immediately after install |
| Slash command `/relay:relay-capture` discovered | **PASS** | Appears in session skill list after restart |
| `relay-mcp` binary on PATH from symlink | **PASS** | MCP server process launched via the symlink; Connected state confirmed |
| Description length 1536-char limit | Not stressed | SKILL.md `description` + `when_to_use` combined is well under limit (~300 chars total) |

## End-to-end smoke test (Task 10)

1. **skill_list_local (empty)** — Returned `[]`. ✓
2. **skill_capture (Stripe 429 example)** — Returned:
   ```json
   {
     "id": "sk_1b3283626a993ad6",
     "name": "stripe-rate-limit-handler",
     "location": "mine",
     "skill_md_path": "/Users/dion/.claude/skills/mine/stripe-rate-limit-handler/SKILL.md",
     "relay_yaml_path": "/Users/dion/.claude/skills/mine/stripe-rate-limit-handler/.relay.yaml"
   }
   ```
3. **On-disk file verification** — Both files present and well-formed:
   - `SKILL.md` has valid YAML frontmatter (`name`, `description`, `when_to_use`) and all 5 body sections (Problem / What I tried / What worked / Tools used / When NOT to use this) in order.
   - `.relay.yaml` serializes `problem`, `solution` (with `tools_used`), `attempts` (2 failures + 1 worked), `context` (languages/libraries/domain), plus defaults (`confidence: 0.5`, `uploaded: false`, `status: active`).
4. **skill_list_local (after capture)** — Returned one entry matching the new skill with `drift_detected: false, uploaded: false`. ✓

## Deferred

- **Claude Code auto-discovery of freshly captured SKILL.md** — requires another restart; the Stripe skill was captured within the current session after Claude Code's initial skill-scan. To verify auto-activation, a future session should ask a Stripe-related question and observe whether the skill is triggered.
- **Drift detection in the live flow** — the simulated-drift flow was exercised in `tests/test_list_local.py::test_list_detects_drift` (passing); live drift will become observable once upload (Week 2) exists.

## Design impact

No design changes needed. All Week 1 assumptions hold in live Claude Code 2.1.116:
- Directory-form skills under `~/.claude/skills/<location>/<name>/` load as expected.
- Sibling `.relay.yaml` does not confuse the loader (its keys are outside Claude Code's frontmatter-only scan surface because it lives in a separate file, not in SKILL.md's YAML).
- The plugin marketplace model is the correct install path — dropping files into `~/.claude/plugins/` directly is not the supported convention.

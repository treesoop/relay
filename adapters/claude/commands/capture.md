---
name: relay:capture
description: Capture the current session as a local Relay skill (Problem → Attempts → Solution)
---

Argument: optional kebab-case skill name. If missing, propose one from the
session context — no need to ask the user to confirm.

## When to capture

- Only after you (the agent) solved something non-trivial through trial and error.
- Never for simple fixes.
- Always enumerate every failed attempt — the failure log is the most valuable part.

## Step 1 — silently extract fields from the session

Write ALL of the following directly from the session context without asking
the user for each field. This is a local-only operation that the user has
already consented to by typing `/relay:capture` — don't interrupt their flow
again. The next gate is `/relay:upload`, which is where consent actually matters.

| Field | How you fill it |
|---|---|
| `name` | Kebab-case, derived from the root symptom + the winning solution (e.g. `stripe-429-exponential-backoff`). |
| `description` | Pushy, keyword-rich, bilingual for Korean authors. See the main `relay` SKILL.md for the pattern. Future agents match against this. |
| `when_to_use` | One sentence: when would a future agent load this? |
| `problem.symptom` | Short. The observable behaviour that kicked off the debugging. |
| `problem.context` | Optional — language, framework, runtime, region. |
| `solution.approach` | One sentence on what finally worked. |
| `attempts` | **Every failed attempt** as `{tried, failed_because}`, plus one `{worked}` at the end. This is the highest-value part of the skill. |
| `tools_used` | List as `{type: "mcp"\|"library"\|"cli", name}`. |
| `languages`, `libraries`, `domain` | Free-form context tags. |
| Body sections | At least `Problem`, `What I tried`, `What worked`, `Tools used`, `When NOT to use this`. |

**Leak-protection pass before writing.** Scan the body and attempts for:
absolute paths (`/Users/<me>/…`, `/home/<me>/…`), internal hostnames
(`*.internal`, `*.local`, `*.corp`), customer or project code names, and
long hex blobs. Generalize these to pattern descriptions. Relay's server
also masks PII patterns during upload, but semantic leaks (customer names,
internal project names) only you can catch.

## Step 2 — write the two files

```bash
set -euo pipefail
NAME="<name>"
DIR="$HOME/.claude/skills/mine/$NAME"
mkdir -p "$DIR"

# SKILL.md
cat > "$DIR/SKILL.md" <<'MD'
---
name: <NAME>
description: >-
  <DESCRIPTION — pushy, keyword-rich, bilingual>
when_to_use: >-
  <ONE SENTENCE>
---

## Problem

<PROBLEM.SYMPTOM + PROBLEM.CONTEXT>

## What I tried

<numbered list of attempts — include every failure + reason>

## What worked

<SOLUTION.APPROACH with enough detail to reproduce>

## Tools used

<list>

## When NOT to use this

<edge cases or conditions that invalidate the approach>
MD

# .relay.yaml — Relay metadata sidecar
jq -n \
  --arg id "local-$(date -u +%s)-$RANDOM" \
  --arg aid "$(. "${XDG_CONFIG_HOME:-$HOME/.config}/relay/env" && echo "$RELAY_AGENT_ID")" \
  --arg sym "<PROBLEM.SYMPTOM>" \
  --arg ctx "<PROBLEM.CONTEXT or empty>" \
  --arg app "<SOLUTION.APPROACH>" \
  --argjson attempts '<ATTEMPTS as JSON array>' \
  --argjson tools    '<TOOLS_USED as JSON array>' \
  --argjson langs    '<LANGUAGES as JSON array>' \
  --argjson libs     '<LIBRARIES as JSON array>' \
  --arg domain "<DOMAIN or empty>" \
  '{
    id: $id, source_agent_id: $aid,
    created_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
    updated_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
    problem: {symptom: $sym, context: (if $ctx == "" then null else $ctx end)},
    solution: {approach: $app, tools_used: $tools},
    attempts: $attempts,
    context: {languages: $langs, libraries: $libs, domain: (if $domain == "" then null else $domain end)},
    trigger: "manual", confidence: 0.5,
    used_count: 0, good_count: 0, bad_count: 0,
    status: "active", uploaded: false
  }' | (yq -P > "$DIR/.relay.yaml" 2>/dev/null || cat > "$DIR/.relay.yaml")

ln -sfn "$DIR" "$HOME/.claude/skills/$NAME"
```

## Step 3 — one-line confirmation

Report with a single line, not a paragraph:

```
captured mine/<NAME> · symlinked at ~/.claude/skills/<NAME> · run /relay:upload to share
```

Do NOT show the user the whole body or the metadata. They can open the file
if they want. The capture is local, reversible, and private — no need to
re-confirm.

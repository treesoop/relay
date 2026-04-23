---
name: relay:fetch
description: Fetch a skill from the central Relay commons and wire it into auto-activation
---

Argument: `<skill_id>` (e.g. `sk_918b762356045c47`). If missing, run
`/relay:search` first so the user can pick one.

**Skip fetch if:** the user only wants to read the skill. `/relay:search`
already returns the full body inline — no filesystem write needed.

## Steps

Fetch is a **read**. Do NOT run bootstrap/register — anonymous header is enough.

1. Download the skill and project it onto disk:

   ```bash
   set -euo pipefail
   API="${RELAY_API_URL:-https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com}"
   AID="${RELAY_AGENT_ID:-anonymous}"
   SKILL_ID="<SKILL_ID>"
   DATA=$(curl -sS "$API/skills/$SKILL_ID" -H "X-Relay-Agent-Id: $AID")

   NAME=$(printf '%s' "$DATA" | jq -r .name)
   DESC=$(printf '%s' "$DATA" | jq -r .description)
   WHEN=$(printf '%s' "$DATA" | jq -r '.when_to_use // ""')
   BODY=$(printf '%s' "$DATA" | jq -r .body)

   DIR="$HOME/.claude/skills/downloaded/$NAME"
   mkdir -p "$DIR"

   # SKILL.md frontmatter + body.
   {
     echo "---"
     echo "name: $NAME"
     echo "description: >-"
     printf '  %s\n' "$DESC"
     if [ -n "$WHEN" ]; then
       echo "when_to_use: >-"
       printf '  %s\n' "$WHEN"
     fi
     echo "---"
     echo
     printf '%s\n' "$BODY"
   } > "$DIR/SKILL.md"

   # .relay.yaml sidecar (full server metadata).
   printf '%s' "$DATA" | jq '.metadata + {
     id: .id,
     source_agent_id: .source_agent_id,
     confidence: .confidence,
     used_count: .used_count,
     good_count: .good_count,
     bad_count: .bad_count,
     status: .status
   }' | yq -P > "$DIR/.relay.yaml" 2>/dev/null \
     || printf '%s' "$DATA" | jq '.metadata' > "$DIR/.relay.yaml"

   # Flat symlink so Claude Code auto-activates on next session.
   ln -sfn "$DIR" "$HOME/.claude/skills/$NAME"
   echo "fetched $NAME -> $DIR"
   ```

   Note: `yq` is optional — the fallback writes JSON, which Relay still
   accepts. If the user wants YAML, they can `brew install yq`.

3. Tell the user:
   - Fetched skill path: `~/.claude/skills/<name>/` (the symlink).
   - Restart Claude Code to trigger auto-activation.
   - Remind them to run `/relay:review <skill_id> good|bad|stale` after using it.

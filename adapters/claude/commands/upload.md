---
name: relay:upload
description: Upload a local mine/<name> skill to the central Relay commons
---

Argument: `<name>`. If missing, list `~/.claude/skills/mine/` and ask which one.

If the sidecar `.relay.yaml` already has a `sk_` id and `uploaded: true`, this
upload will `PATCH` the existing remote skill. The server enforces that only
the original uploader can PATCH (checked against `source_agent_id`).

## Steps

1. Run the shared bootstrap from the `relay` SKILL.md if `~/.config/relay/env` is missing.

2. Preview:

   ```bash
   set -euo pipefail
   source "${XDG_CONFIG_HOME:-$HOME/.config}/relay/env"
   NAME="<NAME>"
   DIR="$HOME/.claude/skills/mine/$NAME"
   [ -d "$DIR" ] || { echo "no mine/$NAME" >&2; exit 1; }
   head -n 20 "$DIR/SKILL.md"
   ```

3. Warn the user: PII in body + `attempts[].failed_because` will be masked
   server-side; the server's masked body is then written back to the local
   SKILL.md so drift detection doesn't fire.

4. Build the payload. The sidecar has Relay metadata; split the SKILL.md into
   its frontmatter and body, then POST or PATCH:

   ```bash
   SECRET=$(jq -r ".agents[\"$RELAY_AGENT_ID\"].secret" \
              "${XDG_CONFIG_HOME:-$HOME/.config}/relay/credentials.json")

   # Split SKILL.md into description/when_to_use (frontmatter) and body.
   DESC=$(awk 'BEGIN{c=0} /^---$/{c++; next} c==1 && /^description:/{sub(/^description:[[:space:]]*/,""); print; exit}' "$DIR/SKILL.md")
   WHEN=$(awk 'BEGIN{c=0} /^---$/{c++; next} c==1 && /^when_to_use:/{sub(/^when_to_use:[[:space:]]*/,""); print; exit}' "$DIR/SKILL.md")
   BODY=$(awk '/^---$/{c++; next} c>=2' "$DIR/SKILL.md")

   # If the front-matter uses `>-` folded style the value spans lines —
   # fall back to reading the skill with a small Python helper or yq if
   # the line-based extraction above yields `>-`.
   if [ "$DESC" = ">-" ] || [ "$WHEN" = ">-" ]; then
     if command -v yq >/dev/null; then
       DESC=$(yq -r '.description' "$DIR/SKILL.md")
       WHEN=$(yq -r '.when_to_use // ""' "$DIR/SKILL.md")
     else
       echo "install yq (brew install yq) to upload skills with folded frontmatter" >&2
       exit 1
     fi
   fi

   # Read the Relay sidecar; convert YAML → JSON (yq -o=json) or parse as YAML.
   META_JSON=$(yq -o=json "$DIR/.relay.yaml" 2>/dev/null || cat "$DIR/.relay.yaml")
   REMOTE_ID=$(printf '%s' "$META_JSON" | jq -r '.id // ""')
   UPLOADED=$(printf '%s' "$META_JSON" | jq -r '.uploaded // false')

   PAYLOAD=$(jq -n \
     --arg name "$NAME" \
     --arg desc "$DESC" \
     --arg when "$WHEN" \
     --arg body "$BODY" \
     --argjson meta "$META_JSON" \
     '{name: $name, description: $desc, when_to_use: (if $when == "" then null else $when end),
       body: $body, metadata: $meta}')

   if [ "$UPLOADED" = "true" ] && [[ "$REMOTE_ID" == sk_* ]]; then
     RESP=$(curl -sS -X PATCH "$RELAY_API_URL/skills/$REMOTE_ID" \
       -H "Content-Type: application/json" \
       -H "X-Relay-Agent-Id: $RELAY_AGENT_ID" \
       -H "X-Relay-Agent-Secret: $SECRET" \
       -d "$PAYLOAD")
     MODE=updated
   else
     RESP=$(curl -sS -X POST "$RELAY_API_URL/skills" \
       -H "Content-Type: application/json" \
       -H "X-Relay-Agent-Id: $RELAY_AGENT_ID" \
       -H "X-Relay-Agent-Secret: $SECRET" \
       -d "$PAYLOAD")
     MODE=created
   fi
   echo "$RESP" | jq '{id, name, mode: "'"$MODE"'"}'
   ```

5. Write the server-masked body back to local and stamp the sidecar:

   ```bash
   NEW_ID=$(echo "$RESP" | jq -r .id)
   NEW_BODY=$(echo "$RESP" | jq -r .body)
   HASH=$(printf '%s' "$NEW_BODY" | shasum -a 256 | awk '{print $1}')

   # Rewrite SKILL.md preserving frontmatter but with the masked body.
   FM=$(awk '/^---$/{print; c++; if(c==2) exit; next} c>=1' "$DIR/SKILL.md")
   {
     printf '%s\n\n' "$FM"
     printf '%s\n' "$NEW_BODY"
   } > "$DIR/SKILL.md"

   # Update sidecar id + uploaded + uploaded_hash.
   META_JSON=$(printf '%s' "$META_JSON" | jq \
     --arg id "$NEW_ID" --arg h "$HASH" \
     '.id = $id | .uploaded = true | .uploaded_hash = $h')
   printf '%s' "$META_JSON" | (yq -P > "$DIR/.relay.yaml" 2>/dev/null \
     || cat > "$DIR/.relay.yaml")
   ```

6. Report: `MODE` (`created` or `updated`), the returned `id`, and the URL
   path `GET /skills/<id>` so the user can verify on the server.

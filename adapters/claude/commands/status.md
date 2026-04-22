---
name: relay:status
description: List every Relay-managed skill and flag local drift
---

No arguments.

## Steps

1. List every Relay skill directory under `~/.claude/skills/{mine,downloaded}/`:

   ```bash
   for loc in mine downloaded; do
     dir="$HOME/.claude/skills/$loc"
     [ -d "$dir" ] || continue
     for skill in "$dir"/*/; do
       [ -d "$skill" ] || continue
       printf '%-12s %s\n' "$loc" "$(basename "$skill")"
     done
   done
   ```

2. For each skill, read `.relay.yaml` if present and emit:

   - `id` (remote `sk_...` if uploaded, else `local-only`)
   - `uploaded` flag
   - `uploaded_hash` vs. `sha256(body of SKILL.md after the frontmatter)` — flag drift when they differ.

   Drift means the user edited the skill after uploading. Suggest
   `/relay:upload <name>` to push the new version (it auto-PATCHes since the
   sidecar already has a matching `id`).

3. Also check the flat symlink layer: `ls -l ~/.claude/skills/ | grep ' -> '`.
   Any skill whose flat symlink is missing or broken is invisible to Claude
   Code's auto-activation. Recreate with:

   ```bash
   ln -sfn "$HOME/.claude/skills/<loc>/<name>" "$HOME/.claude/skills/<name>"
   ```

4. Suggested output:

   ```
   loc         name                                      id                        drift
   mine        apprunner-seoul-unsupported-use-tokyo     sk_918b762356045c47       clean
   mine        stripe-rate-limit-handler                 local-only                 —
   downloaded  qemu-amd64-docker-slow-rebuilds           sk_612517070925d04d       —
   ```

#!/usr/bin/env bash
set -euo pipefail

# Claude Code invokes this with JSON on stdin containing tool-call metadata.
# We maintain a tiny sliding window of recent errors per session and set a
# "capture suggestion" flag when we see recovery (error followed by success).

STATE="$HOME/.relay-hook-state.json"
[ -f "$STATE" ] || echo '{"errors_recent": 0, "last_status": "unknown", "suggest_capture": false}' > "$STATE"

INPUT=$(cat)
# Minimal parsing: treat any non-zero exit or "error" keyword in result as an error.
IS_ERROR=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); r=d.get("result") or {}; print("true" if r.get("error") else "false")' 2>/dev/null || echo "false")

python3 - "$STATE" "$IS_ERROR" <<'PY'
import json, sys
p, is_error = sys.argv[1], sys.argv[2] == "true"
st = json.load(open(p))
if is_error:
    st["errors_recent"] = min(st.get("errors_recent", 0) + 1, 10)
    st["last_status"] = "error"
    st["suggest_capture"] = False
else:
    # Recovery detected: at least one recent error and we just succeeded.
    st["suggest_capture"] = st.get("errors_recent", 0) >= 1 and st.get("last_status") == "error"
    st["last_status"] = "ok"
    st["errors_recent"] = 0
json.dump(st, open(p, "w"))
PY

#!/usr/bin/env bash
set -euo pipefail

# Relay one-line installer.
# Usage: curl -fsSL https://raw.githubusercontent.com/treesoop/relay/main/install.sh | bash
# Or:    ./install.sh
#
# Installs the Relay MCP server locally and wires it into Claude Code via the
# bundled local marketplace. Idempotent — safe to re-run.

REPO_URL="${RELAY_REPO_URL:-https://github.com/treesoop/relay.git}"
INSTALL_DIR="${RELAY_INSTALL_DIR:-$HOME/.relay}"
BIN_DIR="${RELAY_BIN_DIR:-$HOME/.local/bin}"
# Production API. Override via env for self-hosted setups.
DEFAULT_API_URL="${RELAY_API_URL:-https://x4xv5ngcwv.ap-northeast-1.awsapprunner.com}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/relay"
ENV_FILE="$CONFIG_DIR/env"
CRED_FILE="$CONFIG_DIR/credentials.json"

say() { printf "\n\033[1;36m==>\033[0m %s\n" "$*"; }
fail() { printf "\n\033[1;31merror:\033[0m %s\n" "$*" >&2; exit 1; }

# --- preflight ---
command -v git      >/dev/null || fail "git is required"
command -v claude   >/dev/null || fail "Claude Code CLI is required (https://claude.com/claude-code)"

# Find a Python 3.11+ interpreter (prefer specific versions over generic python3).
PY=""
for cand in python3.14 python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null; then
    v=$("$cand" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "")
    case "$v" in
      3.11|3.12|3.13|3.14) PY="$cand"; break ;;
    esac
  fi
done
[ -n "$PY" ] || fail "Python 3.11+ required (found only: $(python3 --version 2>&1 || echo none))"
say "using $PY ($($PY --version))"

# --- clone or update ---
if [ -d "$INSTALL_DIR/.git" ]; then
  say "updating existing install at $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  say "cloning $REPO_URL -> $INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# --- venv + editable install ---
say "setting up virtualenv with $PY"
"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -e ".[dev]" --quiet

# --- symlink relay-mcp onto PATH ---
mkdir -p "$BIN_DIR"
ln -sfn "$INSTALL_DIR/.venv/bin/relay-mcp" "$BIN_DIR/relay-mcp"

case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) say "warning: $BIN_DIR is not on PATH; add it to your shell profile"; ;;
esac

# --- claude plugin ---
if claude plugin list 2>/dev/null | grep -q 'relay@'; then
  say "relay plugin already installed"
else
  say "registering local marketplace"
  claude plugin marketplace add "$INSTALL_DIR" || true
  say "installing relay plugin"
  claude plugin install relay@relay-local
fi

# --- per-machine agent identity ---
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [ -f "$ENV_FILE" ] && grep -q '^RELAY_AGENT_ID=' "$ENV_FILE"; then
  AGENT_ID=$(grep '^RELAY_AGENT_ID=' "$ENV_FILE" | head -1 | cut -d= -f2-)
  say "reusing existing agent id: $AGENT_ID"
else
  HOST=$(hostname -s 2>/dev/null || hostname)
  HOST_SLUG=$(echo "$HOST" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | sed 's/^-//;s/-$//' | cut -c1-24)
  RAND=$("$PY" -c 'import secrets; print(secrets.token_hex(4))')
  AGENT_ID="${HOST_SLUG:-agent}-${RAND}"
  say "generated agent id: $AGENT_ID"
  {
    echo "RELAY_API_URL=$DEFAULT_API_URL"
    echo "RELAY_AGENT_ID=$AGENT_ID"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# Register with the commons so the server has a row + issues a secret.
if [ ! -f "$CRED_FILE" ] || ! grep -q "\"$AGENT_ID\"" "$CRED_FILE"; then
  say "registering $AGENT_ID with $DEFAULT_API_URL"
  REG_RESP=$(curl -sS -X POST "$DEFAULT_API_URL/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"agent_id\":\"$AGENT_ID\"}" || true)
  SECRET=$(echo "$REG_RESP" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("secret") or "")' 2>/dev/null || true)
  if [ -z "$SECRET" ]; then
    fail "registration returned no secret. Response: $REG_RESP"
  fi
  "$PY" - <<PY
import json, os
path = "$CRED_FILE"
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data.setdefault("agents", {})["$AGENT_ID"] = {"secret": "$SECRET"}
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2)
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
fi

say "done."
cat <<EOF

Next:
  1) Restart Claude Code so the MCP server picks up.
  2) Add this to your shell profile so /relay:* commands know the API + your agent id:

       source $ENV_FILE

     Or export manually:
       export RELAY_API_URL=$DEFAULT_API_URL
       export RELAY_AGENT_ID=$AGENT_ID

  3) Try /relay:status in any session.
EOF

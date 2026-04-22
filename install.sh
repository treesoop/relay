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

say "done."
cat <<EOF

Next:
  1) Restart Claude Code so the MCP server picks up.
  2) Try /relay:status in any session.
  3) See $INSTALL_DIR/QUICKSTART.md for the 3-minute walkthrough.
EOF

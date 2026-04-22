#!/usr/bin/env bash
set -euo pipefail

ROOT="${RELAY_SKILL_ROOT:-$HOME/.claude/skills}"

read -rp "Delete ALL skills under $ROOT/{mine,downloaded,staging}? [y/N] " REPLY
case "$REPLY" in
  y|Y|yes|YES) ;;
  *) echo "aborted."; exit 1 ;;
esac

for sub in mine downloaded staging; do
  if [ -d "$ROOT/$sub" ]; then
    rm -rf "$ROOT/$sub"
    echo "  wiped $sub/"
  fi
done

echo "done."

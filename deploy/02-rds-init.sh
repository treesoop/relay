#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

ENDPOINT=$(jq -r .db_endpoint "$STATE")
USER=$(jq -r .db_user "$STATE")
NAME=$(jq -r .db_name "$STATE")
PASS=$(jq -r .db_password "$STATE")

if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "null" ]; then
  echo "ERROR: db_endpoint not in state; run 01-rds-create.sh first." >&2
  exit 1
fi

echo "[1/2] Run central_api/sql/001_init.sql against $ENDPOINT"
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" \
  -v ON_ERROR_STOP=1 \
  -f central_api/sql/001_init.sql

echo "[2/2] Verify schema"
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -c "\d skills" | grep embedding
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -c "SELECT extname FROM pg_extension WHERE extname='vector'"

echo
echo "=== schema initialized ==="

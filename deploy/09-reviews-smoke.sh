#!/usr/bin/env bash
set -euo pipefail

STATE=".aws/deployment-state.json"
URL=$(jq -r .apprunner_service_url "$STATE")

if [ -z "$URL" ] || [ "$URL" = "null" ]; then
  echo "ERROR: no apprunner_service_url in state." >&2; exit 1
fi

AGENT="reviews-smoke-agent"

echo "[1/4] register agent"
curl -sf -X POST "$URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"agent_id\":\"$AGENT\"}" >/dev/null

echo "[2/4] seed skill"
SID=$(curl -sf -X POST "$URL/skills" \
  -H 'Content-Type: application/json' \
  -H "X-Relay-Agent-Id: $AGENT" \
  -d '{
    "name":"review-smoke","description":"test","when_to_use":"never","body":"b",
    "metadata":{
      "problem":{"symptom":"x"},
      "solution":{"approach":"y","tools_used":[]},
      "attempts":[],
      "context":{"languages":[],"libraries":[]}
    }
  }' | jq -r .id)
echo "  seeded: $SID"

echo "[3/4] submit good review"
curl -sf -X POST "$URL/skills/$SID/reviews" \
  -H 'Content-Type: application/json' \
  -H "X-Relay-Agent-Id: $AGENT" \
  -d '{"signal":"good"}' | jq .

echo "[4/4] verify confidence recompute"
RESP=$(curl -sf "$URL/skills/$SID" -H "X-Relay-Agent-Id: $AGENT")
echo "$RESP" | jq '{id, confidence, good_count, bad_count, status}'

CONF=$(echo "$RESP" | jq -r .confidence)
GOOD=$(echo "$RESP" | jq -r .good_count)

if [ "$GOOD" != "1" ]; then
  echo "FAIL: expected good_count=1, got $GOOD" >&2; exit 1
fi
# confidence = (1 + 0.5) / (1 + 0 + 1) = 0.75
python3 -c "import sys; c=float('$CONF'); sys.exit(0 if abs(c - 0.75) < 1e-6 else 1)" || {
  echo "FAIL: expected confidence=0.75, got $CONF" >&2; exit 1
}

echo
echo "=== reviews cloud smoke passed ==="

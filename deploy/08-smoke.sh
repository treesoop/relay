#!/usr/bin/env bash
set -euo pipefail

STATE=".aws/deployment-state.json"
URL=$(jq -r .apprunner_service_url "$STATE")

if [ -z "$URL" ] || [ "$URL" = "null" ]; then
  echo "ERROR: no apprunner_service_url in state." >&2; exit 1
fi

echo "[1/3] GET $URL/health"
curl -sf "$URL/health" || { echo "health check failed"; exit 1; }
echo

echo "[2/3] POST $URL/auth/register"
curl -sf -X POST "$URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"smoke-agent"}' || { echo "register failed"; exit 1; }
echo

echo "[3/3] POST $URL/skills"
curl -sf -X POST "$URL/skills" \
  -H 'Content-Type: application/json' \
  -H 'X-Relay-Agent-Id: smoke-agent' \
  -d '{
    "name": "cloud-smoke",
    "description": "First skill uploaded to the live Relay cloud",
    "when_to_use": "Never in anger; smoke-only",
    "body": "## Problem\nDid it survive deploy?\n## What worked\nApp Runner + RDS + local BGE.\n",
    "metadata": {
      "problem": {"symptom": "deploy shakedown"},
      "solution": {"approach": "just hit it", "tools_used": []},
      "attempts": [],
      "context": {"languages": ["python"], "libraries": []}
    }
  }' | jq '.'

echo
echo "=== smoke test passed ==="

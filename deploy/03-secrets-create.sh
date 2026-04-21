#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

SECRET_NAME="relay/database-url"

ENDPOINT=$(jq -r .db_endpoint "$STATE")
USER=$(jq -r .db_user "$STATE")
NAME=$(jq -r .db_name "$STATE")
PASS=$(jq -r .db_password "$STATE")

DATABASE_URL="postgresql+asyncpg://$USER:$PASS@$ENDPOINT:5432/$NAME"

echo "[1/2] Ensure secret exists"
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
     --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1; then
  echo "  secret exists — updating value"
  aws secretsmanager put-secret-value \
    --secret-id "$SECRET_NAME" \
    --secret-string "$DATABASE_URL" \
    --profile "$PROFILE" --region "$REGION" >/dev/null
else
  echo "  creating secret"
  aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --description "Relay central API DATABASE_URL (asyncpg format)" \
    --secret-string "$DATABASE_URL" \
    --profile "$PROFILE" --region "$REGION" >/dev/null
fi

SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
  --query 'ARN' --output text --profile "$PROFILE" --region "$REGION")

echo "  ARN: $SECRET_ARN"

echo "[2/2] Persist state"
tmp=$(mktemp)
jq --arg arn "$SECRET_ARN" --arg name "$SECRET_NAME" \
   '. + {secret_db_url_arn: $arn, secret_db_url_name: $name}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"
echo
echo "=== secret ready ==="

#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

ACCESS_ROLE="RelayAppRunnerECRAccess"
INSTANCE_ROLE="RelayAppRunnerInstance"
SECRET_ARN=$(jq -r .secret_db_url_arn "$STATE")

TRUST_ACCESS='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
TRUST_INSTANCE='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

echo "[1/4] Access role (ECR pull)"
if ! aws iam get-role --role-name "$ACCESS_ROLE" --profile "$PROFILE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ACCESS_ROLE" \
    --assume-role-policy-document "$TRUST_ACCESS" \
    --profile "$PROFILE" >/dev/null
fi
aws iam attach-role-policy --role-name "$ACCESS_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess \
  --profile "$PROFILE" 2>/dev/null || true

ACCESS_ARN=$(aws iam get-role --role-name "$ACCESS_ROLE" --query Role.Arn --output text --profile "$PROFILE")
echo "  $ACCESS_ARN"

echo "[2/4] Instance role (Secrets Manager read)"
if ! aws iam get-role --role-name "$INSTANCE_ROLE" --profile "$PROFILE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$INSTANCE_ROLE" \
    --assume-role-policy-document "$TRUST_INSTANCE" \
    --profile "$PROFILE" >/dev/null
fi

SECRETS_POLICY='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"'"$SECRET_ARN"'"}]}'

aws iam put-role-policy --role-name "$INSTANCE_ROLE" \
  --policy-name RelaySecretsRead \
  --policy-document "$SECRETS_POLICY" \
  --profile "$PROFILE" >/dev/null

INSTANCE_ARN=$(aws iam get-role --role-name "$INSTANCE_ROLE" --query Role.Arn --output text --profile "$PROFILE")
echo "  $INSTANCE_ARN"

echo "[3/4] Wait for role propagation (~10s)"
sleep 10

echo "[4/4] Persist state"
tmp=$(mktemp)
jq --arg access "$ACCESS_ARN" --arg instance "$INSTANCE_ARN" \
   '. + {apprunner_access_role_arn: $access, apprunner_instance_role_arn: $instance}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"

echo
echo "=== IAM roles ready ==="

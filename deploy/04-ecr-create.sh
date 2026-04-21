#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

REPO_NAME="relay-api"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text --profile "$PROFILE")

echo "[1/2] Ensure ECR repo exists"
if ! aws ecr describe-repositories --repository-names "$REPO_NAME" \
      --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1; then
  aws ecr create-repository --repository-name "$REPO_NAME" \
    --image-scanning-configuration scanOnPush=true \
    --profile "$PROFILE" --region "$REGION" >/dev/null
  echo "  created: $REPO_NAME"
else
  echo "  reusing: $REPO_NAME"
fi

REPO_URI="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"

echo "[2/2] Persist state"
tmp=$(mktemp)
jq --arg uri "$REPO_URI" --arg name "$REPO_NAME" --arg acct "$ACCOUNT" \
   '. + {ecr_repo_uri: $uri, ecr_repo_name: $name, aws_account: $acct}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"

echo
echo "=== ECR ready: $REPO_URI ==="

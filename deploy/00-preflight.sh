#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"

echo "=== Relay deploy preflight ==="
echo "profile: $PROFILE"
echo "region:  $REGION"
echo

echo "[1/5] AWS CLI version"
aws --version

echo "[2/5] Identity"
aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" --output table

echo "[3/5] Region reachable"
aws ec2 describe-regions --region "$REGION" --profile "$PROFILE" \
  --query 'Regions[?RegionName==`ap-northeast-2`].RegionName' --output text

echo "[4/5] Docker buildx"
docker buildx version
docker buildx ls | grep -q default && echo "default builder present"

echo "[5/5] jq"
jq --version

echo
echo "=== preflight OK ==="

#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

REPO_URI=$(jq -r .ecr_repo_uri "$STATE")
if [ -z "$REPO_URI" ] || [ "$REPO_URI" = "null" ]; then
  echo "ERROR: ecr_repo_uri missing from state; run 04-ecr-create.sh first." >&2
  exit 1
fi

TAG="${1:-v$(date -u +%Y%m%d%H%M%S)}"
IMAGE="$REPO_URI:$TAG"
LATEST="$REPO_URI:latest"

echo "[1/4] ECR login"
aws ecr get-login-password --profile "$PROFILE" --region "$REGION" \
  | docker login --username AWS --password-stdin "${REPO_URI%/*}"

echo "[2/4] Ensure buildx builder with QEMU support"
docker buildx inspect relaybuilder >/dev/null 2>&1 || \
  docker buildx create --name relaybuilder --use

# Enable emulation for linux/amd64 (needed on arm64 hosts like Colima on M-series).
docker run --rm --privileged tonistiigi/binfmt --install amd64 >/dev/null 2>&1 || true

echo "[3/4] Build + push (linux/amd64)"
docker buildx build \
  --platform linux/amd64 \
  --file Dockerfile.prod \
  --tag "$IMAGE" \
  --tag "$LATEST" \
  --push \
  .

echo "[4/4] Persist state"
tmp=$(mktemp)
jq --arg image "$IMAGE" --arg tag "$TAG" \
   '. + {ecr_image: $image, ecr_image_tag: $tag}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"

echo
echo "=== pushed: $IMAGE ==="

#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
# App Runner is not available in ap-northeast-2 (Seoul) as of 2026.
# Use ap-northeast-1 (Tokyo) for the service; RDS stays in Seoul (cross-region OK).
REGION="${APPRUNNER_REGION:-ap-northeast-1}"
STATE=".aws/deployment-state.json"

SERVICE_NAME="relay-api"
IMAGE="$(jq -r .ecr_repo_uri "$STATE"):latest"
ACCESS_ROLE_ARN=$(jq -r .apprunner_access_role_arn "$STATE")
INSTANCE_ROLE_ARN=$(jq -r .apprunner_instance_role_arn "$STATE")
SECRET_ARN=$(jq -r .secret_db_url_arn "$STATE")

SERVICE_ARN=$(aws apprunner list-services \
  --query "ServiceSummaryList[?ServiceName=='$SERVICE_NAME'].ServiceArn" --output text \
  --profile "$PROFILE" --region "$REGION")

if [ -n "$SERVICE_ARN" ] && [ "$SERVICE_ARN" != "None" ]; then
  echo "service already exists: $SERVICE_ARN — use start-deployment to redeploy."
else
  echo "creating App Runner service…"

  SOURCE_CFG=$(cat <<EOF
{
  "ImageRepository": {
    "ImageIdentifier": "$IMAGE",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8080",
      "RuntimeEnvironmentVariables": {
        "RELAY_EMBEDDING_PROVIDER": "local",
        "RELAY_EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        "RELAY_EMBEDDING_DIM": "384"
      },
      "RuntimeEnvironmentSecrets": {
        "RELAY_DATABASE_URL": "$SECRET_ARN"
      }
    }
  },
  "AutoDeploymentsEnabled": false,
  "AuthenticationConfiguration": {
    "AccessRoleArn": "$ACCESS_ROLE_ARN"
  }
}
EOF
)

  INSTANCE_CFG=$(cat <<EOF
{
  "Cpu": "1024",
  "Memory": "2048",
  "InstanceRoleArn": "$INSTANCE_ROLE_ARN"
}
EOF
)

  HEALTH_CFG='{"Protocol":"HTTP","Path":"/health","Interval":10,"Timeout":5,"HealthyThreshold":2,"UnhealthyThreshold":3}'

  SERVICE_ARN=$(aws apprunner create-service \
    --service-name "$SERVICE_NAME" \
    --source-configuration "$SOURCE_CFG" \
    --instance-configuration "$INSTANCE_CFG" \
    --health-check-configuration "$HEALTH_CFG" \
    --query 'Service.ServiceArn' --output text \
    --profile "$PROFILE" --region "$REGION")
fi

echo "waiting for service RUNNING (up to ~7 min)…"
for i in $(seq 1 60); do
  STATUS=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" \
    --query 'Service.Status' --output text --profile "$PROFILE" --region "$REGION")
  echo "  [$i] $STATUS"
  [ "$STATUS" = "RUNNING" ] && break
  [ "$STATUS" = "CREATE_FAILED" ] && { echo "service failed to start — check CloudWatch logs"; exit 1; }
  sleep 8
done

URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" \
  --query 'Service.ServiceUrl' --output text --profile "$PROFILE" --region "$REGION")

tmp=$(mktemp)
jq --arg arn "$SERVICE_ARN" --arg url "https://$URL" \
   '. + {apprunner_service_arn: $arn, apprunner_service_url: $url}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"

echo
echo "=== App Runner up: https://$URL ==="

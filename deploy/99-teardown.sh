#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

read -rp "This will DELETE App Runner, ECR, Secrets, RDS. Type 'teardown' to continue: " CONFIRM
[ "$CONFIRM" = "teardown" ] || { echo "aborted."; exit 1; }

# 1. App Runner service
SERVICE_ARN=$(jq -r '.apprunner_service_arn // empty' "$STATE")
if [ -n "$SERVICE_ARN" ]; then
  echo "[1] delete App Runner service"
  aws apprunner delete-service --service-arn "$SERVICE_ARN" \
    --profile "$PROFILE" --region "$REGION" >/dev/null || true
fi

# 2. ECR repo
REPO_NAME=$(jq -r '.ecr_repo_name // empty' "$STATE")
if [ -n "$REPO_NAME" ]; then
  echo "[2] delete ECR repo"
  aws ecr delete-repository --repository-name "$REPO_NAME" --force \
    --profile "$PROFILE" --region "$REGION" >/dev/null || true
fi

# 3. Secret
SECRET_NAME=$(jq -r '.secret_db_url_name // empty' "$STATE")
if [ -n "$SECRET_NAME" ]; then
  echo "[3] delete Secrets Manager entry (scheduled 7-day recovery)"
  aws secretsmanager delete-secret --secret-id "$SECRET_NAME" --recovery-window-in-days 7 \
    --profile "$PROFILE" --region "$REGION" >/dev/null || true
fi

# 4. IAM roles
for role in RelayAppRunnerECRAccess RelayAppRunnerInstance; do
  echo "[4] detach + delete IAM role $role"
  aws iam list-attached-role-policies --role-name "$role" --profile "$PROFILE" \
    --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null | tr '\t' '\n' | \
    while read -r arn; do
      [ -z "$arn" ] && continue
      aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" --profile "$PROFILE" 2>/dev/null || true
    done
  aws iam delete-role-policy --role-name "$role" --policy-name RelaySecretsRead --profile "$PROFILE" 2>/dev/null || true
  aws iam delete-role --role-name "$role" --profile "$PROFILE" 2>/dev/null || true
done

# 5. RDS instance
DB_INSTANCE=$(jq -r '.db_instance_id // empty' "$STATE")
if [ -n "$DB_INSTANCE" ]; then
  echo "[5] delete RDS instance (this takes ~5 min; no final snapshot)"
  aws rds delete-db-instance --db-instance-identifier "$DB_INSTANCE" \
    --skip-final-snapshot --profile "$PROFILE" --region "$REGION" >/dev/null || true
fi

# 6. RDS subnet group (wait for instance to be gone first)
echo "[6] wait for RDS delete, then remove subnet group + SG"
aws rds wait db-instance-deleted --db-instance-identifier "$DB_INSTANCE" \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null || true
aws rds delete-db-subnet-group --db-subnet-group-name relay-subnet \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null || true

DB_SG=$(jq -r '.db_sg_id // empty' "$STATE")
[ -n "$DB_SG" ] && aws ec2 delete-security-group --group-id "$DB_SG" \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null || true

# 7. Clean local state
echo "[7] reset deployment state"
echo '{}' > "$STATE"

echo
echo "=== teardown complete ==="

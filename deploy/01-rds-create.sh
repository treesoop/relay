#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

DB_INSTANCE_ID="relay-pg"
DB_NAME="relay"
DB_USER="relay"
DB_PASS="$(openssl rand -base64 32 | tr -d '+=/' | head -c 28)"
DB_SG_NAME="relay-rds-sg"

mkdir -p .aws
[ -f "$STATE" ] || echo '{}' > "$STATE"

echo "[1/6] Ensure default VPC + subnets exist"
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text --profile "$PROFILE" --region "$REGION")
echo "  default VPC: $VPC_ID"

SUBNETS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'Subnets[].SubnetId' --output text --profile "$PROFILE" --region "$REGION")
echo "  subnets: $SUBNETS"

echo "[2/6] Create or reuse RDS security group"
SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$DB_SG_NAME" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text --profile "$PROFILE" --region "$REGION" 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$DB_SG_NAME" \
    --description "Relay RDS Postgres - public, password auth" \
    --vpc-id "$VPC_ID" --query 'GroupId' --output text \
    --profile "$PROFILE" --region "$REGION")
  echo "  created SG: $SG_ID"

  # Allow 5432 from anywhere (password auth + strong random password = acceptable for MVP)
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port 5432 --cidr 0.0.0.0/0 \
    --profile "$PROFILE" --region "$REGION" >/dev/null
  echo "  ingress 5432/tcp 0.0.0.0/0 added"
else
  echo "  reusing SG: $SG_ID"
fi

echo "[3/6] Create DB subnet group (if missing)"
aws rds describe-db-subnet-groups --db-subnet-group-name relay-subnet \
  --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1 || \
aws rds create-db-subnet-group --db-subnet-group-name relay-subnet \
  --db-subnet-group-description "Relay default VPC subnets" \
  --subnet-ids $SUBNETS \
  --profile "$PROFILE" --region "$REGION" >/dev/null
echo "  subnet group: relay-subnet"

echo "[4/6] Create RDS instance (if missing)"
if aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" \
     --profile "$PROFILE" --region "$REGION" >/dev/null 2>&1; then
  echo "  RDS instance already exists — skipping create"
  DB_PASS="$(jq -r .db_password "$STATE")"
  if [ -z "$DB_PASS" ] || [ "$DB_PASS" = "null" ]; then
    echo "  WARN: no stored password in state. You must re-create the instance or supply the existing password manually." >&2
    exit 1
  fi
else
  echo "  creating RDS instance (this takes ~5-8 minutes)"
  aws rds create-db-instance \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --engine postgres --engine-version 16 \
    --db-instance-class db.t4g.micro \
    --allocated-storage 20 --storage-type gp3 \
    --master-username "$DB_USER" --master-user-password "$DB_PASS" \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$SG_ID" \
    --db-subnet-group-name relay-subnet \
    --publicly-accessible \
    --backup-retention-period 1 \
    --no-multi-az \
    --no-deletion-protection \
    --profile "$PROFILE" --region "$REGION" >/dev/null
  echo "  submitted; waiting until available…"
fi

echo "[5/6] Wait until available"
aws rds wait db-instance-available --db-instance-identifier "$DB_INSTANCE_ID" \
  --profile "$PROFILE" --region "$REGION"

ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text \
  --profile "$PROFILE" --region "$REGION")
echo "  endpoint: $ENDPOINT"

echo "[6/6] Persist state"
tmp=$(mktemp)
jq --arg instance "$DB_INSTANCE_ID" \
   --arg endpoint "$ENDPOINT" \
   --arg user "$DB_USER" \
   --arg name "$DB_NAME" \
   --arg password "$DB_PASS" \
   --arg sg "$SG_ID" \
   --arg vpc "$VPC_ID" \
   '. + {db_instance_id: $instance, db_endpoint: $endpoint, db_user: $user, db_name: $name, db_password: $password, db_sg_id: $sg, vpc_id: $vpc}' \
   "$STATE" > "$tmp" && mv "$tmp" "$STATE"
chmod 600 "$STATE"
echo "  state: $STATE (0600)"
echo
echo "=== RDS ready: postgres://$DB_USER:<hidden>@$ENDPOINT:5432/$DB_NAME ==="

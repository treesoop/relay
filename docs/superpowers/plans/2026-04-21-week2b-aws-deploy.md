# Relay Week 2B — AWS Deployment (RDS + ECR + App Runner)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the working Week 2 + 2C central API stack to AWS: RDS PostgreSQL 16 (with pgvector extension) in Seoul, ECR-hosted `relay-api` container image, AWS App Runner service serving traffic over HTTPS. No OpenAI dependency — local BGE-small embedder is baked into the image. Exit criterion: `https://<app-runner-url>/health` returns `{"status":"ok"}` and an `RELAY_API_URL=<app-runner-url> RELAY_RUN_E2E=1 pytest tests/test_e2e_upload_fetch.py` passes end-to-end against the live cloud stack.

**Architecture:**
- **Region:** `ap-northeast-2` (Seoul). AWS profile `relay` (configured in an earlier session).
- **Compute:** AWS App Runner, 1 vCPU / 2 GB, ECR image source. No VPC connector — the RDS instance is publicly accessible with a strong-random password in Secrets Manager; App Runner reaches it over public internet. This is explicitly the MVP trade-off (simpler, cheaper by ~$30/mo, acceptably secure with proper SG + password hygiene). Production-grade tightening (move RDS to private subnet + VPC connector) is an explicit follow-up plan, not part of 2B.
- **Database:** RDS PostgreSQL 16 on `db.t4g.micro` (free tier for 12 months, ~$15/mo after). pgvector extension enabled on first connect. Schema populated from `central_api/sql/001_init.sql`.
- **Secrets:** AWS Secrets Manager holds `DATABASE_URL` (contains the generated password). App Runner injects it as `RELAY_DATABASE_URL` at runtime.
- **Image:** Multi-step Docker build for `linux/amd64` (App Runner runs x86_64 only as of 2026). Colima arm64 builds via QEMU emulation — slower but correct.
- **Deploy mode:** Manual ECR push + App Runner `start-deployment`. GitHub auto-deploy is not wired in this plan (explicit follow-up — keeps 2B focused on "can we run this in AWS at all").

**Tech Stack:**
- AWS CLI v2 (already installed, profile `relay`)
- Docker + buildx with QEMU multi-arch support
- `jq` (for parsing AWS CLI JSON outputs in scripts)
- Existing `docker-compose.yml` unchanged (still the dev stack); new deploy commands live outside it

---

## Preconditions (satisfied before starting)

- AWS CLI 2.34+ installed; `aws sts get-caller-identity --profile relay` returns `AdministratorAccess` on account `911167924136`.
- Colima docker runtime is up: `docker version` succeeds.
- `jq` installed (used by several tasks for parsing AWS JSON output). If missing: `brew install jq`.
- The `week2` branch has a clean tree (all Week 2C commits landed), tests pass, and the Docker image `relay-api:latest` builds locally.

---

## File Structure

```
relay/
├── .aws/                                    # NEW: deploy-artifact stash (gitignored)
│   └── deployment-state.json                # apparition: ARNs, URLs, timestamps
│
├── deploy/                                  # NEW: deployment scripts + docs
│   ├── README.md                            # runbook: prereqs, 10-line recipe, rollback
│   ├── 00-preflight.sh                      # verify AWS creds, region, docker buildx
│   ├── 01-rds-create.sh                     # create RDS subnet group + instance
│   ├── 02-rds-init.sh                       # install pgvector + run 001_init.sql
│   ├── 03-secrets-create.sh                 # put DATABASE_URL in Secrets Manager
│   ├── 04-ecr-create.sh                     # create ECR repo
│   ├── 05-image-push.sh                     # docker buildx build --platform linux/amd64 + push
│   ├── 06-iam-create.sh                     # App Runner instance role + access role
│   ├── 07-apprunner-create.sh               # create App Runner service from ECR
│   ├── 08-smoke.sh                          # curl /health, register agent, upload+fetch via httpx
│   └── 99-teardown.sh                       # optional: rollback everything
│
├── Dockerfile.prod                          # NEW: prod-variant of central_api/Dockerfile
│                                            #   - no --extra-index-url for torch (default Linux amd64 wheel is fine)
│                                            #   - pip install --no-cache-dir -e "."  (no dev deps)
│
├── .gitignore                               # MODIFY: add .aws/
└── README.md                                # MODIFY: "Deployment" section pointing at deploy/README.md
```

The `deploy/*.sh` scripts are idempotent where safe (they check for existing resources and exit 0 if already present). Each script reads and writes `.aws/deployment-state.json` so subsequent scripts pick up ARNs/IDs without requiring flags.

**Why scripts, not Terraform?** User already decided console-first for MVP; bash + AWS CLI is the minimum viable IaC. A follow-up plan can migrate to Terraform once the pipeline is proven.

---

## Task 0: Preflight + scaffolding

**Files:**
- Create: `.gitignore` update (add `.aws/`)
- Create: `deploy/README.md`
- Create: `deploy/00-preflight.sh`
- Create: `Dockerfile.prod`

- [ ] **Step 1: Extend `.gitignore`**

Append to `.gitignore`:

```
# AWS deployment state
.aws/
```

- [ ] **Step 2: Create deploy directory stub**

```bash
cd /Users/dion/potenlab/our_project/relay
mkdir -p deploy .aws
```

- [ ] **Step 3: Write `deploy/00-preflight.sh`**

```bash
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
```

Make it executable: `chmod +x deploy/00-preflight.sh`.

- [ ] **Step 4: Write `deploy/README.md`** (minimal runbook)

```markdown
# Relay AWS Deployment

Target: `ap-northeast-2` (Seoul). AWS profile: `relay`.

## One-shot provision (first time)

    ./deploy/00-preflight.sh
    ./deploy/01-rds-create.sh         # ~8 min wait for RDS
    ./deploy/02-rds-init.sh
    ./deploy/03-secrets-create.sh
    ./deploy/04-ecr-create.sh
    ./deploy/05-image-push.sh         # ~10 min first build (QEMU amd64)
    ./deploy/06-iam-create.sh
    ./deploy/07-apprunner-create.sh   # ~5 min wait for service RUNNING
    ./deploy/08-smoke.sh

State between steps is written to `.aws/deployment-state.json` (gitignored).

## Redeploy after code change

    ./deploy/05-image-push.sh
    aws apprunner start-deployment --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
      --profile relay --region ap-northeast-2

## Teardown (reversible)

    ./deploy/99-teardown.sh   # deletes App Runner, ECR, Secrets, RDS

## Known constraints

- App Runner runs linux/amd64 only. Colima on arm64 Mac builds via QEMU; expect slow builds.
- RDS is publicly accessible with password auth. Production should move to VPC connector.
- No GitHub auto-deploy wired in this plan — redeploy is a single `aws apprunner start-deployment` call.
```

- [ ] **Step 5: Write `Dockerfile.prod`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY central_api ./central_api
COPY local_mcp ./local_mcp

# Production: no dev deps. torch/sentence-transformers wheel on linux/amd64 is fine from PyPI default.
RUN pip install --no-cache-dir -e "."

# Pre-download the embedding model so cold starts don't stall on a 130MB fetch.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

EXPOSE 8080
CMD ["uvicorn", "--factory", "central_api.main:create_app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 6: Run preflight**

```bash
./deploy/00-preflight.sh
```

Expected: all 5 checks pass, final line `=== preflight OK ===`.

If `jq --version` fails, run `brew install jq` and rerun.

- [ ] **Step 7: Commit**

```bash
git add .gitignore deploy/ Dockerfile.prod
git commit -m "feat(deploy): preflight script + runbook + Dockerfile.prod for AWS"
```

---

## Task 1: RDS PostgreSQL 16 instance

**Files:**
- Create: `deploy/01-rds-create.sh`

- [ ] **Step 1: Write the provisioning script**

```bash
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
    --description "Relay RDS Postgres — public, password auth" \
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
```

`chmod +x deploy/01-rds-create.sh`.

- [ ] **Step 2: Run it**

```bash
./deploy/01-rds-create.sh
```

Expected: progresses through 6 steps; step 5 blocks for ~5–8 minutes; final line prints the endpoint.

If the script errors out before step 6, fix the cause and rerun. The script is idempotent.

- [ ] **Step 3: Verify connection from host**

```bash
ENDPOINT=$(jq -r .db_endpoint .aws/deployment-state.json)
USER=$(jq -r .db_user .aws/deployment-state.json)
NAME=$(jq -r .db_name .aws/deployment-state.json)
PASS=$(jq -r .db_password .aws/deployment-state.json)

PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -c "SELECT version();" 2>&1 | head -5
```

If `psql` is not installed: `brew install postgresql@16`. Expected output begins with `PostgreSQL 16.x` and lists architecture info.

- [ ] **Step 4: Commit**

```bash
git add deploy/01-rds-create.sh
git commit -m "feat(deploy): RDS Postgres 16 provisioning script"
```

---

## Task 2: pgvector extension + schema init

**Files:**
- Create: `deploy/02-rds-init.sh`

- [ ] **Step 1: Write the init script**

```bash
#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
STATE=".aws/deployment-state.json"

ENDPOINT=$(jq -r .db_endpoint "$STATE")
USER=$(jq -r .db_user "$STATE")
NAME=$(jq -r .db_name "$STATE")
PASS=$(jq -r .db_password "$STATE")

if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "null" ]; then
  echo "ERROR: db_endpoint not in state; run 01-rds-create.sh first." >&2
  exit 1
fi

echo "[1/2] Run central_api/sql/001_init.sql against $ENDPOINT"
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" \
  -v ON_ERROR_STOP=1 \
  -f central_api/sql/001_init.sql

echo "[2/2] Verify schema"
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -c "\d skills" | grep embedding
PGPASSWORD="$PASS" psql -h "$ENDPOINT" -U "$USER" -d "$NAME" -c "SELECT extname FROM pg_extension WHERE extname='vector'"

echo
echo "=== schema initialized ==="
```

`chmod +x deploy/02-rds-init.sh`.

- [ ] **Step 2: Run it**

```bash
./deploy/02-rds-init.sh
```

Expected output:
- SQL runs without errors (CREATE EXTENSION / CREATE TABLE statements).
- `\d skills` output shows three `vector(384)` columns.
- `pg_extension` query returns `vector`.

If CREATE EXTENSION fails with "permission denied", the RDS parameter group doesn't have `shared_preload_libraries` configured. For the `vector` extension this normally isn't needed — only `pg_stat_statements` style extensions require preload. If it does fail, the workaround is to connect with the superuser role (which is `$DB_USER` here because we created the instance with that as the master user — RDS grants CREATE EXTENSION rights to the master user for the `vector` extension specifically as of 2024+).

- [ ] **Step 3: Commit**

```bash
git add deploy/02-rds-init.sh
git commit -m "feat(deploy): install pgvector + schema in RDS via local psql"
```

---

## Task 3: Secrets Manager — DATABASE_URL

**Files:**
- Create: `deploy/03-secrets-create.sh`

- [ ] **Step 1: Write the secret provisioning script**

```bash
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
```

`chmod +x deploy/03-secrets-create.sh`. Run:

```bash
./deploy/03-secrets-create.sh
```

Expected: final line `=== secret ready ===` and state file now has `secret_db_url_arn`.

- [ ] **Step 2: Commit**

```bash
git add deploy/03-secrets-create.sh
git commit -m "feat(deploy): put DATABASE_URL in Secrets Manager"
```

---

## Task 4: ECR repository

**Files:**
- Create: `deploy/04-ecr-create.sh`

- [ ] **Step 1: Write the ECR provisioning script**

```bash
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
```

`chmod +x deploy/04-ecr-create.sh`. Run:

```bash
./deploy/04-ecr-create.sh
```

- [ ] **Step 2: Commit**

```bash
git add deploy/04-ecr-create.sh
git commit -m "feat(deploy): create ECR repository for relay-api"
```

---

## Task 5: Build and push image (linux/amd64)

**Files:**
- Create: `deploy/05-image-push.sh`

- [ ] **Step 1: Write the build+push script**

```bash
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
```

`chmod +x deploy/05-image-push.sh`.

- [ ] **Step 2: Run it**

```bash
./deploy/05-image-push.sh
```

Expected: image pushed to ECR. First build may take 10–20 minutes because of QEMU emulation translating arm64 instructions to amd64 for every step (especially the torch install and sentence-transformers model download).

- [ ] **Step 3: Verify image in ECR**

```bash
aws ecr describe-images --repository-name relay-api \
  --profile relay --region ap-northeast-2 \
  --query 'imageDetails[].{digest: imageDigest, tags: imageTags, size_mb: (imageSizeInBytes / 1024 / 1024 | floor)}' \
  --output table
```

Expected: at least one image with `latest` tag, ~1500–2200 MB compressed.

- [ ] **Step 4: Commit**

```bash
git add deploy/05-image-push.sh
git commit -m "feat(deploy): buildx + push relay-api image to ECR (linux/amd64)"
```

---

## Task 6: IAM roles for App Runner

**Files:**
- Create: `deploy/06-iam-create.sh`

App Runner needs **two** roles:
1. **Access role** — lets App Runner pull from ECR.
2. **Instance role** — lets the running service access Secrets Manager.

- [ ] **Step 1: Write the IAM script**

```bash
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
```

`chmod +x deploy/06-iam-create.sh`. Run:

```bash
./deploy/06-iam-create.sh
```

- [ ] **Step 2: Commit**

```bash
git add deploy/06-iam-create.sh
git commit -m "feat(deploy): App Runner IAM roles (ECR access + Secrets instance)"
```

---

## Task 7: Create App Runner service

**Files:**
- Create: `deploy/07-apprunner-create.sh`

- [ ] **Step 1: Write the service-create script**

```bash
#!/usr/bin/env bash
set -euo pipefail

PROFILE="${AWS_PROFILE:-relay}"
REGION="${AWS_REGION:-ap-northeast-2}"
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
```

`chmod +x deploy/07-apprunner-create.sh`.

- [ ] **Step 2: Run it**

```bash
./deploy/07-apprunner-create.sh
```

Expected: service transitions through `CREATING` → `OPERATION_IN_PROGRESS` → `RUNNING`, typically 5–7 minutes. Final line prints the HTTPS URL.

- [ ] **Step 3: Commit**

```bash
git add deploy/07-apprunner-create.sh
git commit -m "feat(deploy): create App Runner service (ECR image, Secrets-injected DATABASE_URL)"
```

---

## Task 8: Smoke test the live endpoint

**Files:**
- Create: `deploy/08-smoke.sh`

- [ ] **Step 1: Write the smoke script**

```bash
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
```

`chmod +x deploy/08-smoke.sh`. Run:

```bash
./deploy/08-smoke.sh
```

Expected:
1. `/health` returns `{"status":"ok"}`.
2. `/auth/register` returns `{"agent_id":"smoke-agent"}`.
3. `/skills` returns a full `SkillResponse` JSON with an `id` starting with `sk_`.

- [ ] **Step 2: Commit**

```bash
git add deploy/08-smoke.sh
git commit -m "feat(deploy): live smoke test — health + register + upload against App Runner"
```

---

## Task 9: E2E test against the cloud

**Files:** none created; this is verification using the existing `tests/test_e2e_upload_fetch.py`.

- [ ] **Step 1: Run the E2E test with the cloud URL**

```bash
cd /Users/dion/potenlab/our_project/relay
source .venv/bin/activate
URL=$(jq -r .apprunner_service_url .aws/deployment-state.json)
RELAY_RUN_E2E=1 RELAY_API_URL="$URL" pytest tests/test_e2e_upload_fetch.py -v
```

Expected: **1 passed**.

What this proves: the same upload+fetch roundtrip that passes against local docker-compose also passes against App Runner + RDS. The E2E test uses httpx so any networking oddity (TLS, path-encoding, cold start) would surface.

- [ ] **Step 2: Record result in the verification doc**

Append to `docs/verification/day0-claude-code-skills.md` (or create `docs/verification/aws-deploy-smoke.md` if that file gets too sprawling):

```markdown
## AWS deploy smoke (Task 9 of Plan 2B)

Date: 2026-04-21
Region: ap-northeast-2
Service URL: <paste URL>
Image: <paste ecr_image tag from state>

Checks:
- /health 200 ✓
- /auth/register 201 ✓
- POST /skills 201 ✓
- E2E upload+fetch roundtrip ✓

Notes: <anything unexpected>
```

- [ ] **Step 3: Commit**

```bash
git add docs/verification/
git commit -m "docs: record AWS deploy smoke + E2E results"
```

---

## Task 10: Teardown script (safety net)

**Files:**
- Create: `deploy/99-teardown.sh`

Why now: we want to be able to wipe everything cleanly when experimenting. Writing this script now costs 10 minutes, prevents the "I can't find where I provisioned that RDS" pain later.

- [ ] **Step 1: Write the teardown script**

```bash
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
```

`chmod +x deploy/99-teardown.sh`.

Do NOT run it yet — this is just to have it in place. Verify the file compiles:

```bash
bash -n deploy/99-teardown.sh && echo "syntax OK"
```

- [ ] **Step 2: Commit**

```bash
git add deploy/99-teardown.sh
git commit -m "feat(deploy): teardown script (reversible full cleanup)"
```

---

## Task 11: README — "Deployment" section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Deployment section**

Insert a new section after `## Privacy and embeddings` in `README.md`:

```markdown
## Deployment

Relay's central API ships to AWS App Runner (Seoul, `ap-northeast-2`) with RDS PostgreSQL 16 + pgvector. All infrastructure lives in `deploy/` as idempotent shell scripts — no Terraform yet, but each script writes its state to `.aws/deployment-state.json` so later steps and redeploys pick up existing ARNs.

### First-time provision

    ./deploy/00-preflight.sh
    ./deploy/01-rds-create.sh        # ~8 min wait
    ./deploy/02-rds-init.sh
    ./deploy/03-secrets-create.sh
    ./deploy/04-ecr-create.sh
    ./deploy/05-image-push.sh        # ~10-20 min first time (QEMU amd64)
    ./deploy/06-iam-create.sh
    ./deploy/07-apprunner-create.sh  # ~5-7 min wait
    ./deploy/08-smoke.sh

### Redeploy after a code change

    ./deploy/05-image-push.sh
    aws apprunner start-deployment \
      --service-arn "$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
      --profile relay --region ap-northeast-2

### Teardown

    ./deploy/99-teardown.sh          # irreversible after Secrets recovery window; confirms first

See `deploy/README.md` for the full runbook and known constraints (App Runner x86_64-only, public RDS, QEMU emulation on arm64 hosts).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add AWS deployment runbook section to README"
```

---

## Exit Criteria for Plan 2B

1. `https://<app-runner-url>/health` returns `{"status":"ok"}` from outside AWS.
2. `RELAY_RUN_E2E=1 RELAY_API_URL=<url> pytest tests/test_e2e_upload_fetch.py -v` passes.
3. `aws rds describe-db-instances --db-instance-identifier relay-pg` shows `db.t4g.micro`, `postgres` 16, status `available`.
4. `aws ecr describe-images --repository-name relay-api` shows at least one image with `latest` tag.
5. `aws apprunner describe-service --service-arn $(jq -r .apprunner_service_arn .aws/deployment-state.json)` shows `Status: RUNNING`.
6. `docs/verification/aws-deploy-smoke.md` (or appended to `day0-claude-code-skills.md`) records the run with URL and image tag.
7. The teardown script exists and `bash -n` passes.

---

## Known limitations (explicit follow-ups, not 2B)

1. **RDS publicly accessible.** MVP trade-off. Follow-up plan will move to a private subnet + VPC connector.
2. **No GitHub auto-deploy.** Every code change requires a manual `docker buildx build --push` + `aws apprunner start-deployment`. Wiring the ECR Events → App Runner auto-deploy trigger (or a GitHub Actions workflow that builds and pushes) is a small dedicated plan.
3. **Single AZ RDS, no Multi-AZ.** For MVP costs. Production should enable Multi-AZ (+~$15/mo on t4g.micro).
4. **No custom domain.** Using the generated `*.ap-northeast-2.awsapprunner.com` URL. Route 53 + ACM cert is a 15-minute plan when needed.
5. **No CloudFront.** App Runner has direct HTTPS; CloudFront only matters for geo distribution or caching — neither applies to our usage.
6. **No CI.** `pytest` is run manually. A GitHub Actions workflow running pytest against a docker-compose stack (no AWS creds) is a follow-up.
7. **IP-allowlisted RDS is not enforced.** We rely on password auth only. Consider adding IP restrictions (App Runner outbound IPs) in a follow-up.

---

## Self-review — performed

- **Spec coverage.** SPEC.md §5 ("Central API endpoints") is already served by Week 2; §8 Week 2 deploy task ("Fly.io 또는 Railway 배포" — revised to AWS per later conversation) is executed in full by Tasks 4–9 (ECR → App Runner). SPEC.md §13 infra list (Docker 24+, PostgreSQL 16 + pgvector, Python 3.11+) is satisfied by the Dockerfile.prod + RDS choices.

- **Placeholder scan.** No "TBD" / "handle edge cases" / "similar to Task N". Every Bash block is fully runnable against a real AWS account.

- **Type consistency across tasks.**
  - `.aws/deployment-state.json` is the single source of truth between tasks; each script reads the keys it needs (`db_endpoint`, `secret_db_url_arn`, etc.) and writes back new keys.
  - The state-key names are globally consistent: `db_instance_id`, `db_endpoint`, `db_user`, `db_name`, `db_password`, `db_sg_id`, `vpc_id`, `secret_db_url_arn`, `secret_db_url_name`, `ecr_repo_uri`, `ecr_repo_name`, `aws_account`, `ecr_image`, `ecr_image_tag`, `apprunner_access_role_arn`, `apprunner_instance_role_arn`, `apprunner_service_arn`, `apprunner_service_url`.
  - `Dockerfile.prod` uses the same `CMD` as `central_api/Dockerfile` (uvicorn --factory) and reads the same `RELAY_EMBEDDING_*` env vars wired in `07-apprunner-create.sh`.

- **Idempotency.** Every provisioning script checks for existing resources before creating them. Re-running the whole pipeline is safe.

- **Scope discipline.** No changes to application code in `central_api/` or `local_mcp/` — this plan only adds deploy artifacts. The application has already proven it works in docker-compose; 2B moves it to AWS without touching business logic.

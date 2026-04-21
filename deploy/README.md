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

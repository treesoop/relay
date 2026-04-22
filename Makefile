.PHONY: help install test up down reset-local deploy-redeploy smoke metrics

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install deps in existing venv
	pip install -e ".[dev]"

test: ## Run the full test suite
	pytest -q

up: ## Start docker-compose (postgres + api)
	docker compose up -d
	@echo "api: http://localhost:8080"

down: ## Stop docker-compose
	docker compose down

reset-local: ## Wipe ~/.claude/skills/{mine,downloaded,staging}
	./scripts/reset-local.sh

deploy-redeploy: ## Rebuild image + trigger App Runner deploy
	./deploy/05-image-push.sh
	aws apprunner start-deployment \
	  --service-arn "$$(jq -r .apprunner_service_arn .aws/deployment-state.json)" \
	  --profile relay --region ap-northeast-1

smoke: ## Run cloud smoke tests against live App Runner
	./deploy/08-smoke.sh
	./deploy/09-reviews-smoke.sh

metrics: ## Dump central DB metrics (requires RELAY_DATABASE_URL)
	python scripts/metrics.py

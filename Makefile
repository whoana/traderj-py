.PHONY: help install test engine-test api-test dashboard-test lint lint-fix type-check format up down build rebuild logs health emergency-stop migrate migrate-down db-backup clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Install ---
install: ## Install all dependencies
	cd shared && pip install -e .
	cd engine && poetry install
	cd api && poetry install
	cd dashboard && pnpm install

# --- Test ---
engine-test: ## Run engine tests with coverage
	cd engine && pytest tests/ -v --cov=engine --cov-report=term-missing

api-test: ## Run API tests with coverage
	cd api && pytest tests/ -v --cov=api --cov-report=term-missing

dashboard-test: ## Run dashboard tests
	cd dashboard && pnpm test

test: engine-test api-test dashboard-test ## Run all tests

# --- Lint ---
lint: ## Lint all Python code
	ruff check shared/ engine/ api/

lint-fix: ## Auto-fix lint issues
	ruff check --fix shared/ engine/ api/

type-check: ## Run mypy type checking
	cd engine && mypy engine/ --strict
	cd api && mypy api/ --strict

format: ## Format all Python code
	ruff format shared/ engine/ api/

# --- Docker ---
up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build all Docker images
	docker compose build

rebuild: ## Rebuild images without cache
	docker compose build --no-cache

# --- Logging & Monitoring ---
logs: ## Tail all service logs
	docker compose logs -f

health: ## Check service health
	@echo "API Health:"
	@curl -sf http://localhost:8000/api/v1/health | python -m json.tool 2>/dev/null || echo "  Not responding"
	@echo "\nEngine Metrics:"
	@curl -sf http://localhost:8001/metrics | head -5 2>/dev/null || echo "  Not responding"

emergency-stop: ## Emergency stop all trading
	curl -X POST http://localhost:8000/api/v1/bots/emergency-stop-all -H "X-API-Key: $${TRADERJ_API_KEY}"

# --- Database ---
migrate: ## Run Alembic migrations
	cd migrations && alembic upgrade head

migrate-down: ## Rollback one migration
	cd migrations && alembic downgrade -1

db-backup: ## Backup PostgreSQL database
	docker compose exec postgres pg_dump -U traderj traderj > backup_$$(date +%Y%m%d_%H%M%S).sql

# --- Cleanup ---
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	cd dashboard && rm -rf .next node_modules/.cache 2>/dev/null || true

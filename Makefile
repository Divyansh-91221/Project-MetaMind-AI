# Enterprise Metadata Copilot - developer commands
# Works with GNU Make (Linux/macOS/WSL/Git Bash). Windows users can run the
# underlying commands directly or use `scripts/dev.ps1`.

COMPOSE ?= docker compose
BACKEND_DIR := backend
PY ?= python

.DEFAULT_GOAL := help
.PHONY: help install install-frontend up down logs ps build migrate revision seed demo \
        run run-frontend test test-unit test-integration lint format typecheck check \
        precommit clean reset-db

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install backend dependencies + pre-commit hooks
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r $(BACKEND_DIR)/requirements.txt
	pre-commit install

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

up: ## Start the full local stack
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Tail service logs
	$(COMPOSE) logs -f --tail=100

ps: ## Show container status
	$(COMPOSE) ps

build: ## Rebuild container images
	$(COMPOSE) build

migrate: ## Apply database migrations
	cd $(BACKEND_DIR) && alembic upgrade head

revision: ## Create a new migration: make revision m="add x"
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(m)"

seed: ## Load demo enterprise metadata and lineage
	$(PY) scripts/seed_demo_data.py

demo: up ## Full local demo: containers + migrations + demo data
	$(COMPOSE) exec backend alembic -c alembic.ini upgrade head
	$(COMPOSE) exec backend $(PY) /app/scripts/seed_demo_data.py

run: ## Run the API locally with autoreload
	uvicorn app.main:app --app-dir $(BACKEND_DIR) --reload --port 8000

run-frontend: ## Run the Vite dev server
	cd frontend && npm run dev

test: ## Run the whole backend test suite
	pytest

test-unit: ## Run unit tests only
	pytest -m unit

test-integration: ## Run integration tests (requires Postgres + Neo4j)
	pytest -m integration

lint: ## Lint with ruff
	ruff check backend scripts tests

format: ## Format with black + ruff --fix
	black backend scripts tests
	ruff check --fix backend scripts tests

typecheck: ## Static type check
	mypy backend/app

check: lint typecheck test ## Lint + types + tests

precommit: ## Run all pre-commit hooks
	pre-commit run --all-files

reset-db: ## Drop and recreate volumes (DESTRUCTIVE - local only)
	$(COMPOSE) down -v

clean: ## Remove local caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

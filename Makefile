# llm-router — convenience targets. Requires Docker + the compose plugin.
.DEFAULT_GOAL := help
SHELL := /bin/bash

.PHONY: help build up down restart logs ps smoke failover refresh-check refresh-write genkey

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

build: ## Build the image (native arm64)
	docker compose build

up: ## Build + start in the background
	docker compose up -d --build

down: ## Stop and remove the container
	docker compose down

restart: ## Recreate the container (picks up .env + config changes)
	docker compose up -d --force-recreate litellm

logs: ## Follow proxy logs
	docker compose logs -f litellm

ps: ## Show container status
	docker compose ps

smoke: ## Run the smoke test against the running proxy
	./scripts/smoke.sh

failover: ## Prove real failover (poison Gemini -> expect Groq), then restore
	./scripts/failover_test.sh

refresh-check: ## Show what the openrouter-free block WOULD become (no writes)
	python3 scripts/refresh_models.py --check

refresh-write: ## Regenerate the openrouter-free block and restart if it changed
	python3 scripts/refresh_models.py --write --restart

genkey: ## Print a fresh master key for .env
	@echo "sk-$$(openssl rand -hex 32)"

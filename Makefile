SHELL := /usr/bin/env bash
UV ?= uv
.DEFAULT_GOAL := help

.PHONY: help setup sync format lint quality pre-commit test check
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

format.markdown: ## Run mdformat
	$(UV) run mdformat && $(UV) run mdformat --check .

format.python: ## Run ruff for formatting
	$(UV) run ruff format .
	$(UV) run ruff check --fix-only --fix --unsafe-fixes .

typecheck: ## Run ty for typechecking
	$(UV) run ty check --config-file ty.toml

setup: ## Setup Developer Environment
	bash ./scripts/setup.sh

sync: ## Sync all workspace packages and dependency groups
	$(UV) sync --all-packages --all-groups

format: ## Run the quality script's formatters
	bash ./scripts/format.sh

lint: ## Run the quality script's linters
	bash ./scripts/lint.sh

test: ## Run the quality script's tests
	./scripts/quality.sh --test

quality: ## Run the full quality script
	./scripts/quality.sh

pre-commit: ## Run pre-commit on all files
	$(UV) run pre-commit run --all-files

check: lint test ## Run lint then test

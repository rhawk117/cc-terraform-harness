SHELL := /usr/bin/env bash
UV ?= uv
.DEFAULT_GOAL := help

.PHONY: help setup sync format lint quality pre-commit test test.end-to-end check
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

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

format: ## Run the prek format hooks on all files
	$(UV) run prek run --all-files --group format

lint: ## Run the prek lint hooks on all files
	$(UV) run prek run --all-files --group lint

test: ## Run the unit, agents and smoke tests
	$(UV) run pytest -q -m "unit or agents or smoke"

test.end-to-end: ## Run the end-to-end tests
	$(UV) run pytest -q -m e2e

quality: ## Run every prek hook on all files, then the tests CI runs
	$(UV) run prek run --all-files
	$(UV) run pytest -q -m "not integration"

pre-commit: ## Run every prek hook on all files
	$(UV) run prek run --all-files

check: lint test ## Run lint then test

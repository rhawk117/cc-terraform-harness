#!/usr/bin/env bash
set -euo pipefail

readonly LOGGING_UTILS="./scripts/log.sh"

setup_environment() {
  local repository_root
  repository_root=$(git rev-parse --show-toplevel)
  cd "$repository_root"

  # shellcheck disable=SC1090
  source "$LOGGING_UTILS"
}

main() {
  setup_environment

  log::step "installing pre-commit hook"
  uv run pre-commit install --install-hooks
  log::step_end

  log::step "syncing dependency groups"
  uv sync --all-packages --all-groups
  log::step_end

  log::success "development environment setup"
}

main "$@"

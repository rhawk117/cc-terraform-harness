#!/usr/bin/env bash
set -euo pipefail

readonly LOGGING_UTILS="./scripts/log.sh"

FAILURES=()

setup_environment() {
  local repository_root
  repository_root=$(git rev-parse --show-toplevel)
  cd "$repository_root"

  # shellcheck disable=SC1090
  source "$LOGGING_UTILS"
}

run_step() {
  local label=$1
  local exit_code=0
  shift

  log::step "$label"
  "$@" || exit_code=$?
  log::step_end

  if ((exit_code != 0)); then
    FAILURES+=("$label")
  fi

  return 0
}

write_format() {
  run_step "ruff format" uv run ruff format .
  run_step "ruff lint autofix" uv run ruff check --fix --unsafe-fixes --fix-only .
  run_step "shfmt" uv run shfmt -w -i 2 -ci .
  run_step "mdformat" uv run mdformat .
}

main() {
  setup_environment
  write_format

  if [[ -n "${FAILURES[*]-}" ]]; then
    log::error "Failed checks: ${FAILURES[*]}"
    exit 1
  fi
}

main "$@"

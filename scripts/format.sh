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

files_with_extension() {
  local pattern=$1
  shift
  git ls-files -z -- "$pattern" | xargs -0 -r -- "$@" --
}

write_format() {
  run_step "ruff format" files_with_extension '*.py' uv run ruff format
  run_step "ruff lint autofix" files_with_extension '*.py' uv run ruff check --fix --unsafe-fixes --fix-only
  run_step "shfmt" files_with_extension '*.sh' uv run shfmt -w -i 2 -ci
  run_step "mdformat" files_with_extension '*.md' uv run mdformat
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

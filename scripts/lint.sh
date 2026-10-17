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

linter_checks() {
  run_step "Ruff Check" uv run ruff check --show-fixes -q .
  run_step "Typecheck" uv run ty check --config-file ty.toml --output-format concise .
  run_step "Shellcheck" files_with_extension '*.sh' uv run shellcheck
  run_step "Shellformat" files_with_extension '*.sh' uv run shfmt -d -i 2 -ci
  run_step "Markdown" files_with_extension '*.md' uv run mdformat --check
}

main() {
  setup_environment
  linter_checks

  if [[ -n "${FAILURES[*]-}" ]]; then
    log::error "Failed checks: ${FAILURES[*]}"
    exit 1
  fi

  log::info "all linting checks passed"
}

main "$@"

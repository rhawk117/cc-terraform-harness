#!/usr/bin/env bash

set -uo pipefail
shopt -s globstar

readonly RUFF_CONFIG=(--config ruff.toml --force-exclude)
readonly MARKDOWN_GLOBS=(**/*.md *.md)

FAILURES=()

run_step() {
  local label=$1
  shift

  log::info "${label}"
  "$@" || {
    FAILURES+=("${label}")
    return 1
  }
}

usage() {
  printf 'usage: %s [--format | --lint | --test]\n' "${0##*/}" >&2
}

run_formatter() {
  run_step 'Ruff Format' uv run ruff format "${RUFF_CONFIG[@]}" .
  run_step 'Ruff Fix' uv run ruff check "${RUFF_CONFIG[@]}" --fix-only --unsafe-fixes .
  run_step 'Markdown Format' uv run mdformat "${MARKDOWN_GLOBS[@]}"
}

run_linter() {
  run_step 'Ruff Format Check' uv run ruff format "${RUFF_CONFIG[@]}" --check .
  run_step 'Ruff Check' uv run ruff check "${RUFF_CONFIG[@]}" --no-fix .
  run_step 'Markdown Check' uv run mdformat --check "${MARKDOWN_GLOBS[@]}"
  run_step 'Typecheck' uv run ty check --config-file ty.toml
}

main() {
  repository_root=$(git rev-parse --show-toplevel) || return 1
  cd "${repository_root}" || return 1

  # shellcheck disable=SC1091
  source scripts/log.sh

  case "${1:-}" in
    --format) run_formatter ;;
    --lint) run_linter ;;
    '')
      run_formatter
      run_linter
      ;;
    *)
      usage
      return 2
      ;;
  esac

  if ((${#FAILURES[@]} > 0)); then
    log::error 'quality checks failed:'
    printf '  - %s\n' "${FAILURES[@]}" >&2
    return 1
  fi

  log::success 'quality checks passed'
}

main "$@"

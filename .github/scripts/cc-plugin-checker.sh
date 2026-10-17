#!/usr/bin/env bash
set -euo pipefail

readonly LOGGING_UTILS="./scripts/log.sh"
readonly CLAUDE_CODE_RELEASE_CHANNEL="stable"
readonly CLAUDE_CODE_PACKAGE="@anthropic-ai/claude-code"

setup_environment() {
  local repository_root
  repository_root=$(git rev-parse --show-toplevel)
  cd "$repository_root"

  # shellcheck disable=SC1090
  source "$LOGGING_UTILS"
}

install_claude_code() {
  local version target

  version=$(
    npm view \
      "${CLAUDE_CODE_PACKAGE}@${CLAUDE_CODE_RELEASE_CHANNEL}" \
      version
  )
  target="${CLAUDE_CODE_PACKAGE}@${version}"

  log::step "Install Claude Code CLI ($version)"
  npm install -g "$target"
  log::step_end
}

validate_plugin() {
  log::step "Validating Plugin Contents"
  claude plugin validate --strict .
  log::step_end
}

main() {
  setup_environment
  install_claude_code
  validate_plugin
}

main "$@"

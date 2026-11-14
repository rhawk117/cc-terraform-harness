#!/usr/bin/env bash
# Checks that this machine has what the terraform-harness Claude Code plugin needs.
#
#   bash precheck.sh
#   curl -fsSL https://raw.githubusercontent.com/rhawk117/cc-terraform-harness/main/precheck.sh | bash
#
# Exit status: 0 when every required tool is present, 1 when one is missing.
# A missing optional tool prints a warning and does not change the exit status.
set -uo pipefail

# Stops terraform -version from calling HashiCorp's update-check service.
export CHECKPOINT_DISABLE=1

if [[ -t 1 && -z ${NO_COLOR:-} ]]; then
  readonly C_OK=$'\033[0;32m' C_WARN=$'\033[1;33m' C_ERR=$'\033[0;31m'
  readonly C_DIM=$'\033[2m' C_BOLD=$'\033[1m' C_RESET=$'\033[0m'
else
  readonly C_OK='' C_WARN='' C_ERR='' C_DIM='' C_BOLD='' C_RESET=''
fi

MISSING_REQUIRED=0
MISSING_OPTIONAL=0
OS_KIND=''

report_ok() {
  printf '  %s✔%s %-13s %s%s%s\n' "$C_OK" "$C_RESET" "$1" "$C_DIM" "$2" "$C_RESET"
}

report_missing() {
  local level=$1 name=$2 why=$3 hint=$4 color=$C_ERR mark='✘'
  if [[ $level == optional ]]; then
    color=$C_WARN
    mark='!'
  fi
  printf '  %s%s %-13s%s missing (%s)\n' "$color" "$mark" "$name" "$C_RESET" "$level"
  printf '      %s\n' "$why"
  printf '      install: %s\n' "$hint"
}

detect_os() {
  case "$(uname -s)" in
    Darwin) OS_KIND=macos ;;
    Linux)
      OS_KIND=linux
      if grep -qi microsoft /proc/version 2>/dev/null; then
        OS_KIND=wsl
      fi
      ;;
    MINGW* | MSYS* | CYGWIN*) OS_KIND=windows ;;
    *) OS_KIND=unknown ;;
  esac
}

check_os() {
  case "$OS_KIND" in
    macos | linux | wsl)
      report_ok 'platform' "$OS_KIND"
      ;;
    windows)
      MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
      report_missing required 'platform' \
        'Native Windows is not supported: the hooks start through a sh script.' \
        'run Claude Code inside WSL (https://learn.microsoft.com/windows/wsl/install)'
      ;;
    *)
      report_ok 'platform' "$(uname -s) (untested; Linux, macOS and WSL are supported)"
      ;;
  esac
}

# Picks the install hint for this OS: macOS gets the Homebrew command, others get the generic one.
pick_hint() {
  local generic=$1 macos=${2:-}
  if [[ $OS_KIND == macos && -n $macos ]]; then
    printf '%s' "$macos"
  else
    printf '%s' "$generic"
  fi
}

# check_tool LEVEL NAME VERSION_FLAG WHY GENERIC_HINT [MACOS_HINT]
check_tool() {
  local level=$1 name=$2 version_flag=$3 why=$4 generic_hint=$5 macos_hint=${6:-}
  local version

  if command -v "$name" >/dev/null 2>&1; then
    version=$("$name" "$version_flag" 2>/dev/null | head -n 1)
    report_ok "$name" "${version:-installed}"
    return 0
  fi

  if [[ $level == required ]]; then
    MISSING_REQUIRED=$((MISSING_REQUIRED + 1))
  else
    MISSING_OPTIONAL=$((MISSING_OPTIONAL + 1))
  fi
  report_missing "$level" "$name" "$why" "$(pick_hint "$generic_hint" "$macos_hint")"
}

check_required_tools() {
  printf '\n%sRequired%s\n' "$C_BOLD" "$C_RESET"
  check_os
  check_tool required claude --version \
    'Claude Code loads the plugin.' \
    'curl -fsSL https://claude.ai/install.sh | bash  (see https://code.claude.com/docs/en/setup)'
  check_tool required uv --version \
    'The MCP server and every hook start through uv run; it also fetches Python 3.14.' \
    'curl -LsSf https://astral.sh/uv/install.sh | sh  (see https://docs.astral.sh/uv/getting-started/installation/)' \
    'brew install uv'
  check_tool required git --version \
    'The change_impact tool and the trace-change-impact skill read the git diff.' \
    'your package manager, e.g. sudo apt install git  (see https://git-scm.com/downloads)' \
    'xcode-select --install  or  brew install git'
  check_tool required terraform -version \
    'The hooks and the MCP server run terraform fmt, validate and providers schema.' \
    'https://developer.hashicorp.com/terraform/install' \
    'brew tap hashicorp/tap && brew install hashicorp/tap/terraform'
}

check_optional_tools() {
  printf '\n%sOptional%s %s(the plugin works without these, with the checks that need them skipped)%s\n' \
    "$C_BOLD" "$C_RESET" "$C_DIM" "$C_RESET"
  check_tool optional tflint --version \
    'The read hook and the diagnostics tool lint modules with it.' \
    'curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash  (see https://github.com/terraform-linters/tflint#installation)' \
    'brew install tflint'
  check_tool optional terraform-ls --version \
    'The language server for .tf and .tfvars files; the subagents fall back to Grep without it.' \
    'https://github.com/hashicorp/terraform-ls/blob/main/docs/installation.md' \
    'brew install hashicorp/tap/terraform-ls'
}

print_summary() {
  printf '\n'
  if ((MISSING_REQUIRED > 0)); then
    printf '%s%d required prerequisite(s) missing.%s Install them, then run this script again.\n' \
      "$C_ERR" "$MISSING_REQUIRED" "$C_RESET"
    return 1
  fi

  if ((MISSING_OPTIONAL > 0)); then
    printf '%sReady, with %d optional tool(s) missing.%s\n' "$C_WARN" "$MISSING_OPTIONAL" "$C_RESET"
  else
    printf '%sAll prerequisites found.%s\n' "$C_OK" "$C_RESET"
  fi
  printf 'Next: install the plugin (https://github.com/rhawk117/cc-terraform-harness#install).\n'
  printf '%sNetwork access is needed the first time uv builds the plugin environments.%s\n' \
    "$C_DIM" "$C_RESET"
}

main() {
  printf '%sterraform-harness prerequisite check%s\n' "$C_BOLD" "$C_RESET"
  detect_os
  check_required_tools
  check_optional_tools
  print_summary
}

main "$@"

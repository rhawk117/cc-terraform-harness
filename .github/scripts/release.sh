#!/usr/bin/env bash

set -euo pipefail

readonly PACKAGE_NAME="${PACKAGE_NAME:-tf-harness-plugin}"
readonly VERSION_BUMP="${VERSION_BUMP:-recover}"
readonly LOGGING_UTILS="./scripts/log.sh"
readonly PLUGIN_MANIFEST=".claude-plugin/plugin.json"
readonly RELEASE_BOT_USERNAME="github-actions[bot]"
readonly RELEASE_BOT_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"

release_version=""
release_tag=""

panic() {
  log::error "$*"
  exit 1
}

setup_environment() {
  local repository_root
  repository_root=$(git rev-parse --show-toplevel)
  cd "$repository_root"

  # shellcheck disable=SC1090
  source "$LOGGING_UTILS"
}

validate_release_context() {
  [[ "${GITHUB_EVENT_NAME:-}" == workflow_dispatch ]] || panic "Releases require workflow_dispatch."

  [[ "${GITHUB_REF:-}" == refs/heads/main ]] || panic "Releases must originate from main."

  [[ "${REPOSITORY_IS_FORK:-true}" == false ]] || panic "Releases are disabled in forks."

  case "$VERSION_BUMP" in
    recover | major | minor | patch) ;;
    *) panic "Invalid version bump: $VERSION_BUMP" ;;
  esac
}

validate_current_release() {
  log::step "Validate Current Release"

  release_version=$(uv version --package "$PACKAGE_NAME" --short)
  release_tag="v${release_version}"

  local manifest_version
  manifest_version=$(jq -er '.version | strings' "$PLUGIN_MANIFEST")

  [[ "$manifest_version" == "$release_version" ]] ||
    panic "Plugin manifest and package versions differ."

  git show-ref --verify --quiet "refs/tags/$release_tag" ||
    panic "Previous release tag does not exist: $release_tag"

  log::step_end
}

bump_release() {
  log::step "Bump Release Version ($VERSION_BUMP)"

  [[ -z "$(git status --porcelain)" ]] ||
    panic "Working tree is not clean."

  uv version --package "$PACKAGE_NAME" --bump "$VERSION_BUMP" --no-sync

  release_version=$(uv version --package "$PACKAGE_NAME" --short)
  release_tag="v${release_version}"

  if git show-ref --verify --quiet "refs/tags/$release_tag"; then
    panic "Release tag already exists: $release_tag"
  fi

  log::step_end
}

synchronize_plugin_manifest() {
  log::step "Synchronize Plugin Manifest"

  jq --arg version "$release_version" \
    '.version = $version' \
    "$PLUGIN_MANIFEST" >"${PLUGIN_MANIFEST}.tmp"

  mv "${PLUGIN_MANIFEST}.tmp" "$PLUGIN_MANIFEST"
  uv lock --check

  log::step_end
}

record_version_bump() {
  log::step "Record Version Bump ($release_tag)"

  git config user.name "${RELEASE_BOT_USERNAME}"
  git config user.email "${RELEASE_BOT_EMAIL}"

  git add -- pyproject.toml uv.lock "$PLUGIN_MANIFEST"

  git commit -m "release: $release_tag"
  git tag -a "$release_tag" -m "Release $release_tag"

  git push --atomic origin \
    HEAD:refs/heads/main \
    "refs/tags/$release_tag:refs/tags/$release_tag"

  log::step_end
}

write_release_outputs() {
  {
    printf 'version=%s\n' "$release_version"
    printf 'tag=%s\n' "$release_tag"
  } >>"${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
}

main() {
  setup_environment
  validate_release_context
  validate_current_release

  if [[ "$VERSION_BUMP" != recover ]]; then
    bump_release
    synchronize_plugin_manifest
    record_version_bump
  fi

  write_release_outputs
}

main "$@"

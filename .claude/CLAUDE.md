# mightymodels: agent instructions

## Commands

Every command goes through `make`. Each target delegates to uv or to a script under `scripts/`: `format.sh` holds the format steps and `lint.sh` the lint steps.

- `make setup` installs the pre-commit git hook and syncs every workspace package and dependency group. A fresh clone has no git hook, so run it before the first commit.
- `make sync` syncs the workspace packages and dependency groups.
- `make format` runs the formatters.
- `make lint` runs ruff check, ty, shellcheck, shfmt and mdformat without fixing anything.
- `make typecheck` runs ty alone.
- `make test` runs pytest with coverage.
- `make pre-commit` runs every pre-commit hook on all files, including the hygiene fixers and uv-lock.
- `make check` runs lint, then test.
- `make quality` runs format, lint and test.

## Stack

Python 3.14 (`.python-version`), uv, ruff, ty, pytest, mdformat and pre-commit. `.github/actions/bootstrap/action.yml` defines the CI setup and pins uv 0.13.1 and Claude Code 2.1.301.

## Layout

- The plugin sits at the repository root, and `.claude-plugin/plugin.json` contains its manifest. The root `pyproject.toml` is both the plugin project and the uv workspace root, with members under `packages/`.
- `packages/mcp` holds the terraform MCP server (`tf_harness_mcp`), which `.mcp.json` launches and whose tests live in `packages/mcp/tests`. There is no `packages/hooks` package yet: the hook code that runs today is `.claude/hooks/pyhooks.py`, a PEP 723 script that `.claude/settings.json` wires to Write, Edit and Read. ty does not check it, because `ty.toml` includes only `packages` and `tests`.
- Read `.claude/rules/python.md` before writing Python and `.claude/rules/testing.md` before writing tests. Both load on their own when you touch a matching file.

## Conventions

- Commit subjects follow Conventional Commits as the history does: `type(scope): subject`, with the subject in lowercase imperative and no closing period. The types in use are feat, fix, ci, build, style and docs.
- The plugin version lives in both `pyproject.toml` and `.claude-plugin/plugin.json`. `tests/test_release_metadata.py` fails when they differ, and the release workflow (`.github/workflows/cd.yml`) bumps both.

## Boundaries

- Always: run the Verification commands before calling work done.
- Ask first: edits to `pyproject.toml`, `uv.lock`, `ruff.toml`, `pytest.toml` and `ty.toml`, which `.claude/settings.json` lists under `permissions.ask`; version bumps, which the release workflow owns; changes to `.claude/settings.json` or `.claude/hooks/pyhooks.py`, because every session runs the hooks they define.
- Never: weaken the ruff or ty configuration; hand-edit `uv.lock`, which the uv-lock hook regenerates; commit `.mightymodels/`, which stays a local-only git exclusion (`SECURITY.md`).

## Verification

`.github/workflows/ci.yml` defines CI's quality job, which runs the pre-commit hooks on all files and then the tests. Match it with `make pre-commit`, then `make test`. `make check` is the faster local loop, but it skips the hygiene and uv-lock hooks, so it can pass where CI fails.

`make test` also runs each package's tests, because `testpaths` in `pytest.toml` collects `packages/*/tests`. For a change confined to `packages/mcp`, `uv run pytest -q packages/mcp/tests` is the faster loop.

## Claude Code

- Inside the Bash sandbox, whole-tree checks (`make lint`, `make check`, `make pre-commit`) can fail on sandbox mount points such as `.mcp.json` or `.claude/skills`, which show up as character devices. A failure that names one of those paths comes from the sandbox, not the repository: report it rather than changing code to get past it.
- The project hooks run on every tool call: before a Write or Edit, a check asks for approval when the change adds a lint or type suppression; after it, the formatter runs; after a Read, ruff and ty report diagnostics on the file.

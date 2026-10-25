# cc-terraform-harness

[![CI](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/ci.yml/badge.svg?event=pull_request)](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/ci.yml)
[![Weekly Supply Chain Audit](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/weekly-security-scan.yml/badge.svg?branch=main)](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/weekly-security-scan.yml)
[![Create Release](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/cd.yml/badge.svg?branch=main)](https://github.com/rhawk117/cc-terraform-harness/actions/workflows/cd.yml)
[![Latest release](https://img.shields.io/github/v/release/rhawk117/cc-terraform-harness?sort=semver)](https://github.com/rhawk117/cc-terraform-harness/releases/latest)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-3776AB?logo=python&logoColor=white)](.python-version)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

terraform-harness is a Claude Code plugin for Terraform and IaC repositories. It adds a Terraform MCP server, four subagents, eight skills, the terraform-ls language server, and hooks that format and check `.tf` files as Claude works. The hooks and the MCP server run only the commands on a fixed allowlist: the `fmt` hook formats the file Claude just wrote, and nothing else writes. Neither one runs `terraform init`, `plan` or `apply`.

The plugin installs as `terraform-harness` from the [rygentic-harness](https://github.com/rhawk117/rygentic-harness) marketplace.

## Prerequisites

| You need | Why |
| --- | --- |
| [Claude Code](https://code.claude.com/docs/en/setup) | It loads the plugin. CI validates the plugin with Claude Code 2.1.301. |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) on your `PATH` | The MCP server and the hooks start through `uv run`. |
| Python 3.14 or newer | The MCP server and hook packages require it. uv downloads it when it is missing, so there is nothing to install by hand. |
| Linux, macOS or WSL | The hooks start through a `sh` script, `bin/tf-harness-hooks`. Native Windows is not supported. |
| `git` | The `change_impact` tool and the trace-change-impact skill read the git diff. |
| [`terraform`](https://developer.hashicorp.com/terraform/install) on your `PATH` | The hooks and the MCP server run `terraform fmt`, `validate` and `providers schema`. |
| [`tflint`](https://github.com/terraform-linters/tflint#installation) on your `PATH` | The read hook and the `diagnostics` tool lint modules with it. |
| [`terraform-ls`](https://github.com/hashicorp/terraform-ls/blob/main/docs/installation.md) on your `PATH` | It is the language server for `.tf` and `.tfvars` files. |
| Network access | uv downloads packages, and Python if needed, the first time it builds each environment. |

The plugin does not require particular tool versions. It was developed against terraform 1.15.8, tflint 0.64.0 and terraform-ls 0.39.0.

> [!NOTE]
> A missing tool does not stop the plugin from installing. Without uv, each hook prints `uv is not on PATH` and skips, and the MCP server cannot start. When `terraform`, `tflint` or `terraform-ls` is missing, the session-start hook names it, and the checks that need it are skipped.

## Install

In Claude Code:

```text
/plugin marketplace add rhawk117/rygentic-harness
/plugin install terraform-harness@rygentic-harness
```

Or from a shell:

```sh
claude plugin marketplace add rhawk117/rygentic-harness
claude plugin install terraform-harness@rygentic-harness
```

The marketplace pins each release to its tag and commit and clones it over HTTPS, so you do not need a GitHub SSH key.

## Set up a repository

Start a new Claude Code session in your Terraform repository, then:

1. Read the session-start output. It lists the terraform, tflint and terraform-ls versions, or names the ones that are missing:

   ```text
   terraform: 1.15.8
   tflint: 0.64.0
   terraform-ls: 0.39.0
   ```

2. Run `/mcp` and check that the `terraform` server from terraform-harness is connected. The first start can take a moment while uv builds its environment.

3. Run `terraform init` in each module you work on. `terraform validate` and the `provider_schema` tool need the providers installed, and the plugin never runs `init` for you.

4. If `.tflint.hcl` declares plugins, run `tflint --init`. The plugin never runs it either, and the read hook tells you when plugins are missing.

> [!TIP]
> To set up a toolchain from scratch, or tighten the one you have, run `/terraform-harness:onboard-toolchain`. It interviews you, then sets up a pinned, verified toolchain, improving what the repository already has rather than replacing it.

## What's included

### Skills

Claude picks a skill from what you ask ("is this plan safe to apply?", "review this module"). You can also run any skill except writing-terraform as `/terraform-harness:<skill>`.

| Skill | What it does |
| --- | --- |
| `check-module` | Runs fmt, validate and tflint on a module directory and reports what passed, failed or was skipped. |
| `explain-plan` | Explains a Terraform plan in plain language, with the verdict first. |
| `fix-review-findings` | Works through a review-module report one finding at a time with terraform-author. It runs only as a slash command: `/terraform-harness:fix-review-findings APPLY-CALYPSE-REPORT.md`. |
| `look-up-schema` | Looks up the attributes and nested blocks of a provider, resource or data source. |
| `onboard-toolchain` | Interviews you and sets up a pinned, verified Terraform toolchain for the repository, improving what exists rather than replacing it. |
| `review-module` | Reviews and grades Terraform code, a repository or a branch, and writes `APPLY-CALYPSE-REPORT.md`. |
| `trace-change-impact` | Traces which blocks, variables, outputs and root modules a change touches. |
| `writing-terraform` | The authoring procedure Claude follows when it writes or edits Terraform, with paired good and bad HCL keyed to the review-module rubric. It loads on its own for `.tf`, `.tfvars` and `.tftest.hcl` files. |

### Agents

| Agent | What it does |
| --- | --- |
| `terraform-advisor` | Gives an expert second opinion on a Terraform question that the primary agent or you cannot settle alone. |
| `terraform-author` | Writes Terraform inside a scope the primary agent hands it, such as a module, a resource, an edit or tests. |
| `terraform-edit-reviewer` | Checks a just-edited module for drift that the edit may have introduced. |
| `terraform-researcher` | Answers one question about a Terraform repository, such as what depends on a path or how risky a plan is. |

### Hooks

| Hook | When it runs | What it does |
| --- | --- | --- |
| `fmt` | After a Write or Edit | Formats the changed `.tf` or `.tfvars` file with `terraform fmt`. |
| `read` | After a Read | Runs `terraform validate` and `tflint`, including any plugins that `.tflint.hcl` configures, in the read file's directory, and reports the diagnostics. |
| `session-start` | When a session starts, clears or compacts | Reports the terraform, tflint and terraform-ls versions, or which of them are missing or could not run. |

### MCP server

The plugin launches `tf-harness-mcp` as the `terraform` MCP server, rooted at the project directory. None of its tools change anything.

| Tool | What it does |
| --- | --- |
| `describe` | Summarizes one Terraform module, `.tf` file or `.tfvars` file. |
| `diagnostics` | Checks one module directory with fmt, validate and tflint. |
| `plan_digest` | Summarizes one plan JSON document, the output of `terraform show -json`. |
| `change_impact` | Reports what a git diff changed in Terraform and which root modules it reaches. |
| `provider_schema` | Reads one level of a provider, resource or data source schema. |

### Language server

`.lsp.json` starts `terraform-ls serve` for `.tf` and `.tfvars` files.

## Development

You need the prerequisites above, plus `make` and `bash`. uv installs the Python tooling (ruff, ty, pytest, pre-commit, shellcheck, shfmt and mdformat), and the `claude` CLI runs `claude plugin validate` and the evals.

```sh
git clone https://github.com/rhawk117/cc-terraform-harness.git
cd cc-terraform-harness
make setup
```

`make setup` installs the pre-commit git hook and syncs every workspace package and dependency group. To try your working copy instead of the installed release, start Claude Code with `claude --plugin-dir .`.

| Command | What it runs |
| --- | --- |
| `make sync` | Syncs the workspace packages and dependency groups. |
| `make format` | The formatters. |
| `make lint` | ruff check, ty, shellcheck, shfmt and mdformat, without fixing anything. |
| `make typecheck` | ty alone. |
| `make test` | pytest with coverage, over `tests/` and each package's tests. |
| `make check` | lint, then test. |
| `make pre-commit` | Every pre-commit hook on all files, including the hygiene fixers and uv-lock. |
| `make quality` | format, lint and test. |

CI's quality job runs the pre-commit hooks on all files, then the tests. To match it before you open a pull request, run `make pre-commit`, then `make test`. `make check` is faster, but it skips the hygiene and uv-lock hooks, so it can pass where CI fails. Tests that need `terraform` or `tflint` are skipped when the tool is not on your `PATH`.

### Layout

| Path | What lives there |
| --- | --- |
| `.claude-plugin/plugin.json` | The plugin manifest. Its version must match `pyproject.toml`. |
| `skills/`, `agents/` | The skills and subagents. |
| `hooks/hooks.json`, `.mcp.json`, `.lsp.json` | The hook, MCP server and language server registrations. |
| `packages/mcp` | The MCP server, `tf_harness_mcp`, and its tests. |
| `packages/hooks` | The hooks, `tf_harness_hooks`, run through the `tf-harness-hooks` CLI, and their tests. |
| `evals/` | `claude plugin eval` cases. |
| `tests/` | Plugin-level tests. |

### Evals

```sh
claude plugin eval . --case s7-onboard-toolchain
```

> [!WARNING]
> `claude plugin eval` refuses a plugin that contains a hard-linked file, and uv can install files into `.venv` as hard links. If every case fails within seconds and the per-run `error` in the JSON report mentions a hard link, reinstall in copy mode, then check that the `find` prints nothing:
>
> ```sh
> UV_LINK_MODE=copy uv sync --all-packages --all-groups --reinstall-package tf-harness-hooks
> find . -type f -links +1 -not -path './.git/*'
> ```

## Security

See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## License

[Apache License 2.0](LICENSE)

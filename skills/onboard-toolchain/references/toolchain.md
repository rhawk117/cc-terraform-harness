# Toolchain layer model

Each layer lists what the discovery script checks, what "present" means, and which repo type needs it. Applies-to values: Root (deploys environments), Module (published for reuse), Both.

## versions (Both)

Present means: `required_version` in every root module, `required_providers` with constraints for every provider, `.terraform.lock.hcl` committed per root module, a tool version file (`.terraform-version` plus `aqua.yaml`, `mise.toml`, or `.tool-versions`), and every non-local module source pinned (`version =` for registry sources, `?ref=` for git sources).

Why it matters: unpinned providers and tools are the most common cause of CI that passes one week and fails the next with no code change.

## format-validate (Both)

Present means: `terraform fmt -check` and `terraform validate` run both in CI and as pre-commit hooks. Running only one place is `partial`.

## lint (Both)

Present means: `tflint` runs in CI and pre-commit, and `.tflint.hcl` declares the provider ruleset plugin with an explicit `version =`. A `.tflint.hcl` without a pinned plugin is `partial`.

For module repos, the rule subset used by terraform-aws-modules doubles as an interface contract: `terraform_deprecated_interpolation`, `terraform_deprecated_index`, `terraform_unused_declarations`, `terraform_comment_syntax`, `terraform_documented_outputs`, `terraform_documented_variables`, `terraform_typed_variables`, `terraform_module_pinned_source`, `terraform_naming_convention`, `terraform_required_version`, `terraform_required_providers`, `terraform_standard_module_structure`, `terraform_workspace_remote`.

## security-scan (Both)

Present means: `trivy config` or `checkov` runs in CI and pre-commit, CI scans plan JSON (not just the HCL directory), and no `tfsec` reference remains.

Trivy facts worth knowing: it absorbed tfsec and tfsec is unmaintained; it evaluates variables and modules, accepts `--tf-vars`, scans downloaded modules by default (`--tf-exclude-downloaded-modules` to skip), can scan a plan file or plan JSON, supports custom Rego checks, needs network access to fetch its checks bundle unless configured for air-gap, and moved live cloud scanning (`trivy aws`) to a plugin from v0.53.

Prefer plan JSON for anything that gates merges. HCL scanning sees defaults; plan scanning sees final values.

## policy (Both)

Present means: a directory of Rego policies exists and `conftest test` (or `opa eval`) runs against plan JSON in CI, and the HCL uses `validation` or `precondition` blocks where invariants exist.

This is the layer a security team should care about most. It is the only control that sees evaluated values across variables and modules. Org rules (no public buckets, mandatory tags, allowed regions) belong here, separate from the generic scanner.

Sentinel is HCP Terraform only; on the open-source CLI, OPA is the option.

## docs (Module primarily, agent file Both)

Present means: `terraform-docs` runs in pre-commit and is checked in CI, README carries `BEGIN_TF_DOCS` / `END_TF_DOCS` markers, `.terraform-docs.yml` exists, and an agent instruction file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, or `.github/copilot-instructions.md`) describes local commands and pre-commit gates.

Root repos often have no consumable interface to document; treat the terraform-docs rows as skippable for them if the user agrees. The agent file is not skippable.

## cost (Root, optional)

`infracost` posting a diff on PRs. Reported as `optional`; never a gap on its own.

## structure (Both)

Present means: root modules declare a remote backend with locking (S3 with `use_lockfile`, GCS, Azure Blob, or an HCP `cloud` block). Module repos legitimately have none; confirm in the interview and treat the row as not applicable.

Orchestrator presence (terragrunt, terramate, atmos, atlantis) is `info`. If one exists, route every command through it.

State handling rules: encrypt at rest, restrict read access like production secrets, never commit `*.tfstate`.

## ci (Root primarily, lint rows Both)

Present means: a pipeline exists; plan runs on PR with the output posted as a comment; a scheduled plan detects drift; cloud auth is OIDC with no static credential secrets; every workflow step has a `name:`.

Apply steps are outside this skill: an existing one is preserved as is, a missing one is never added.

Named steps are not cosmetic. A failed run with unnamed steps reads as `Run actions/checkout@v4` and `Run ...` and is hard to triage.

## automation (Both)

Present means: Renovate or Dependabot config exists. Renovate is preferred because it covers Terraform providers, module sources, tflint plugins, GitHub Actions, and tool version files in one config.

Release automation (conventional commits, `release-please` or `semantic-release`) is `optional`; required for module repos, skip for root repos.

## hygiene (Both)

Present means: `CODEOWNERS` exists and `.gitignore` excludes `.terraform/`, `*.tfstate`, `*.tfstate.*`, and plan files.

## local-loop (Both)

Present means: `.pre-commit-config.yaml` uses `antonbabenko/pre-commit-terraform` with a pinned `rev`, and a task runner (Makefile, Taskfile, justfile) mirrors the CI commands so local and CI never diverge.

## Version compatibility

Use the repository's existing pins or versions supplied by the user, then apply these checks before pinning:

| Pair | Rule |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Terraform vs `required_version` | The pinned CLI must satisfy every root module's constraint. If a constraint excludes the latest, keep the constraint and pin within it, then note the ceiling in the report. |
| Terraform vs providers | Provider constraints in `required_providers` and the lockfile decide; do not bump providers as part of tooling work unless the user adds a row for it. |
| tflint vs ruleset plugin | Each ruleset release states the minimum tflint it needs in its README or release notes. Pin the ruleset to a release compatible with the pinned tflint. When unsure, pin both to their latest and confirm `tflint --init` succeeds. |
| pre-commit-terraform vs binaries | The hooks call whatever `terraform`, `tflint`, `trivy`, `terraform-docs`, and `checkov` are on PATH. The `rev` must be recent enough to know the hook ids you use (`terraform_trivy` replaced `terraform_tfsec`). Confirm with `pre-commit run --all-files`. |
| trivy vs CI | Pin the exact version in CI (`aquasecurity/setup-trivy` or the install script with a version). Unpinned trivy has broken pipelines on minor releases. |
| conftest vs OPA | conftest bundles its own OPA; only pin conftest unless the repo also runs `opa` directly. |
| Renovate vs version files | Renovate needs its `terraform` and `asdf`/`mise`/`aqua` managers enabled to keep the pins current; the default `config:recommended` preset does not cover all of them. |

## Minimum sets

Root-module repo: pinned Terraform, providers, lockfile, tools; fmt, validate, tflint with ruleset; plan on PR posted as comment; OIDC with a read-only plan role; encrypted locking remote state; conftest on plan JSON; trivy config on plan JSON, pinned; Renovate; scheduled drift plan; CODEOWNERS, branch protection, AGENTS.md; centralized reusable workflows once more than one repo exists.

Module repo: everything above that applies, plus the curated tflint rule set, terraform-docs enforced in CI, `examples/` planned on every PR, conventional commits with PR title linting and release automation, and a repo template with README re-sync.

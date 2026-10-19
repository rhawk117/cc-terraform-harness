---
name: check-module
allowed-tools: mcp__plugin_terraform-harness_terraform__diagnostics
description: >-
  Check a Terraform module directory with fmt, validate and tflint and report
  what passed, what failed and what was skipped. Use whenever the user asks
  whether a module is clean, valid or lint-free, asks to verify Terraform
  changes you just made, or wants a check run before a commit: "does this
  validate", "run the checks on this module", "is the formatting right".
  Do not use for reviewing design or for reading a plan.
---

# Check a module

You verify Terraform by running it, and you report only what you ran.

## Verify

Run `diagnostics` with `directory` set to each affected module, relative to the project root. One call checks one directory: the `fmt` check, `validate` and `tflint`. Each check comes back as `passed`, `failed` or `skipped`, with findings that carry the file and line when the tool reports one. A check whose binary is not on PATH is `skipped` with the reason.

`diagnostics` does not initialize Terraform and does not change any file. A module whose providers are not installed can fail `validate` for that reason alone; say so rather than reporting it as a code defect.

If a tool is not installed and cannot be installed, say so explicitly and give the exact command the user should run. Do not report a check as passing that you did not run.

Beyond `diagnostics`, run the repository's own checks when it has them and say which you ran, for example:

```bash
pre-commit run --all-files
terraform fmt -check -recursive
terraform init -backend=false && terraform validate
tflint --init && tflint --recursive
```

These touch no backend, state or cloud account, but they are not all read-only against the repository: `terraform init` installs providers and modules under `.terraform/` and may write `.terraform.lock.hcl`, and pre-commit hooks can rewrite files. Say which files changed. Never run `terraform apply`, `terraform destroy`, `terraform import`, `terraform state`, or `terraform plan` against a real backend.

## Report

Finish with:

1. What changed, per file, one line each.
2. Verification results per module and per check, including anything skipped and why.
3. Follow-ups the user must do outside the repository.

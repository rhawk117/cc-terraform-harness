---
name: check-module
allowed-tools: mcp__plugin_terraform-harness_terraform__diagnostics mcp__plugin_terraform-harness_terraform__plan_digest
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

### Reading validate failures

Clean, idiomatic HCL often fails `validate` because it uses arguments the locked provider does not have. Name the review-module rubric rule for each failure, and check the fix against the `provider_schema` tool, not memory:

| `validate` says | Rule | What it usually means |
| --- | --- | --- |
| `An argument named "..." is not expected here`, `Blocks of type "..." are not expected here`, `does not support resource type` | VE7 | An argument, block or type that does not exist in the locked provider's schema |
| `Reference to undeclared resource` or `module` | DE5 | A rename or removal that missed a reference |
| `Reference to undeclared input variable` | IN8 | A variable used where it is not declared |
| `The argument "..." is required`, `Insufficient ... blocks` | IN10 | A required argument or nested block left out |
| `Duplicate provider configuration` | ST7 | A provider configured twice without an `alias`, or inside a child module |
| A deprecation warning | VE6 | An idiom the locked provider major has superseded |

If the repository already provides a plan rendered as JSON (`terraform show -json` output), run `plan_digest` with `path` set to its location relative to the project root, and report what it returned before using its actions or risk flags. It refuses a binary plan file or a path outside the project root. Neither `diagnostics` nor `plan_digest` creates a plan or initializes Terraform.

If a tool is not installed and cannot be installed, say so explicitly and give the exact command the user should run. Do not report a check as passing that you did not run.

Beyond `diagnostics`, run the repository's own checks when it has them and say which you ran, for example:

```bash
pre-commit run --all-files
terraform fmt -check -recursive
terraform init -backend=false && terraform validate
tflint --init && tflint --recursive
trivy config --exit-code 0 .
conftest verify --policy policy
```

These touch no backend, state or cloud account, but they are not all read-only against the repository: `terraform init` installs providers and modules under `.terraform/` and may write `.terraform.lock.hcl`, and pre-commit hooks can rewrite files. Say which files changed. `conftest verify` runs the policy's own Rego tests; `conftest test` against a plan is a CI concern and is not run here unless the user hands you a `plan.json` they already produced. Never run `terraform apply`, `terraform destroy`, `terraform import`, `terraform state`, or `terraform plan` against a real backend.

For CI files you cannot execute, at minimum parse them (`python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' <file>` if PyYAML is present, otherwise a careful read) and confirm every step you added has a `name:` and every step that existed before still exists with its original name and content.

## Report

Finish with:

1. What changed, per file, one line each.
2. Verification results per module and per check, including anything skipped and why.
3. Follow-ups the user must do outside the repository.

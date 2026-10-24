# cc-terraform-harness

A deterministic Claude Code plugin acting as a harness for terraform and IAC repositories.

## Agents

- `terraform-advisor`: gives an expert second opinion on a Terraform question that the primary agent or user cannot settle alone.
- `terraform-author`: writes Terraform inside a scope the primary agent hands it, such as a module, a resource, an edit or tests.
- `terraform-edit-reviewer`: checks a just-edited module for drift that the edit may have introduced.
- `terraform-researcher`: answers one question about a Terraform repository, such as what depends on a path or how risky a plan is.

## Skills

- `check-module`: runs fmt, validate and tflint on a module directory and reports what passed, failed or was skipped.
- `explain-plan`: explains a Terraform plan in plain language, with the verdict first.
- `fix-review-findings`: works through a review-module report one finding at a time with terraform-author, and is invoked only as a slash command.
- `look-up-schema`: looks up the attributes and nested blocks of a provider, resource or data source.
- `onboard-toolchain`: interviews the user and sets up a pinned, verified Terraform toolchain for the repository, improving what exists rather than replacing it.
- `review-module`: reviews and grades Terraform code, a repository or a branch.
- `trace-change-impact`: traces which blocks, variables, outputs and root modules a change touches.
- `writing-terraform`: the authoring procedure Claude follows when it writes or edits Terraform, with paired good and bad HCL keyed to the review-module rubric. It loads on its own for `.tf`, `.tfvars` and `.tftest.hcl` files.

## Hooks

- `fmt`: runs after a Write or Edit to format the changed `.tf` or `.tfvars` file.

- `read`: runs after a Read to report diagnostics on the `.tf` or `.tfvars` file.

  The read hook runs `terraform validate` and `tflint` (including any plugins that `.tflint.hcl` configures) in the read file's directory on every `.tf` or `.tfvars` Read.

- `session-start`: runs when a session starts, clears or compacts, and reports the terraform, tflint and terraform-ls versions, or which of them are missing or could not run.

## MCP server

- `terraform`: a Terraform MCP server (`tf-harness-mcp`) that the plugin launches against the project root.

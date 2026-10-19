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
- `look-up-schema`: looks up the attributes and nested blocks of a provider, resource or data source.
- `review-module`: reviews and grades Terraform code, a repository or a branch.
- `trace-change-impact`: traces which blocks, variables, outputs and root modules a change touches.

## Hooks

- `fmt`: runs after a Write or Edit to format the changed file.

- `read`: runs after a Read to report diagnostics on the file.

  The read hook runs `terraform validate` and `tflint` (including any plugins that `.tflint.hcl` configures) in the read file's directory on every `.tf` or `.tfvars` Read.

- `session-start`: runs when a session starts, clears or compacts.

## MCP server

- `terraform`: a Terraform MCP server (`tf-harness-mcp`) that the plugin launches against the project root.

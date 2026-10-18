# tf-harness-mcp

An MCP server that gives Claude read-only views of a Terraform project. Every tool takes paths relative to the project root, or absolute inside it.

## Tools

- `diagnostics` runs the terraform fmt check, terraform validate and tflint on one module directory.
- `plan_digest` summarizes a plan rendered by `terraform show -json`.
- `describe` lists the variables, outputs, resources, modules and providers of a module, `.tf` file or `.tfvars` file.
- `provider_schema` reads one level of a provider, resource or data source schema.
- `change_impact` reports what a git diff changed in Terraform and which root modules it reaches.

## Launch

The plugin's `.mcp.json` starts it with `uv run --project ${CLAUDE_PLUGIN_ROOT}/packages/mcp tf-harness-mcp --project-root ${CLAUDE_PROJECT_DIR}`.

## Settings

Each setting is a `TF_HARNESS_<FIELD>` environment variable or a kebab-case flag, for example `--project-root`:

- `project_root`
- `validate_timeout_seconds`
- `lint_timeout_seconds`
- `schema_timeout_seconds`
- `git_timeout_seconds`
- `schema_cache_dir`
- `output_budget_bytes`
- `output_budget_max_bytes`
- `plan_read_cap_bytes`

## Tests

```
uv run pytest -q packages/mcp/tests
```

CI does not run these.

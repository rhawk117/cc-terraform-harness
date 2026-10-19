---
name: look-up-schema
allowed-tools: mcp__plugin_terraform-harness_terraform__provider_schema
description: >-
  Look up the exact schema of a Terraform provider, resource or data source:
  which attributes exist, which are required, optional, computed, sensitive or
  deprecated, and which nested blocks exist. Use before writing or editing a
  resource block, and whenever you are unsure of an argument name, type or
  nesting. Do not guess attribute names from memory.
---

# Look up a schema

Read the schema from the module's own locked provider instead of recalling it.

Call `provider_schema` with:

- `path`: the module directory, relative to the project root.
- `type`: a resource or data source type such as `aws_instance`, or the provider's local name such as `aws` when `kind` is `provider`.
- `kind`: `resource`, `data_source` or `provider`.
- `block`: optional dotted path such as `ebs_block_device` or `a.b`, to read a nested block or nested attribute instead of the top level.

The provider comes from the module's `required_providers`, or is `hashicorp/<prefix>` when undeclared. The module must be initialized with a `.terraform.lock.hcl` entry for the provider; if the call fails for that reason, say so and ask the user to run `terraform init` instead of guessing.

The result gives the locked provider version beside the configuration's version constraint, the level's attributes (type, required, optional, computed, sensitive, deprecated, description) and one summary per nested block (nesting mode, min and max items, attribute and block counts). Read the top level first, then call again with `block` for each nested block you need.

Report the locked version with what you found, since schemas change between versions. Treat a deprecated attribute as a warning to the user, not something to use.

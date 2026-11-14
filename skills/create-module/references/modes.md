Per-mode steps for create-module: what to inventory, how to shape the interface and the moved map, and the default chunks. Read only the section for the mode in use, during steps 1 to 3 of the procedure.

## new: a module from a description

Inventory

- What concept the module raises (a "network", an "upload bucket"), which roots will call it, and which values differ between those callers. The values that differ are the interface; everything else is the module body.
- What the repository already has: an existing module that does most of it (extend it instead, through refactor mode), the naming and tagging conventions, the provider version locked in the callers.

Interface

- Start from `${CLAUDE_PLUGIN_ROOT}/skills/writing-terraform/assets/module-skeleton/`: copy it, then rename and reshape. It already validates against the AWS provider `~> 6.0` and its tests use `command = plan` with `mock_provider`.
- Dependencies come in as inputs (`vpc_id`, `kms_key_arn`, `subnet_ids`); the module does not create or look up what the caller owns.
- A module that is one resource with its arguments passed through is a thin wrapper. Say so and ask whether it is still wanted before planning it.

Default chunks

| id | title | outcome |
| --- | --- | --- |
| C1 | module: versions, variables, resources, outputs | no-changes |
| C2 | tests, README, examples/basic | no-changes |
| C3 | one per caller root the user wants wired: the module call | create-only |

Leave C3 out when the user asked only for the module.

## extract: lift resources out of a root into a module call

Inventory

- Every `resource` and `module` address that will move, with its `count` or `for_each`. Data sources move without state, so they need no `moved` block.
- Every reader of a moving address inside the root: outputs, other resources, `depends_on`, alarms, IAM policies, `.tftest.hcl` files. Use `LSP` `findReferences` on each address, or `rg` when terraform-ls is absent. Readers outside the root (another root's `terraform_remote_state`) read outputs, so the root's output names and values must stay the same.
- The variables and locals the moving code reads: each becomes a module input, and the root passes its current value.
- Provider configuration stays in the root. A resource that used an aliased provider needs `configuration_aliases` in the module and a `providers` map on the call.

Interface and moved map

- Keep each resource's local name inside the module (`aws_vpc.main` becomes `module.network.aws_vpc.main`) unless the user asks for renames: the moved map stays one line per resource and the diff stays readable.
- A whole resource moves in one block, all its instances at once: `from = aws_subnet.private`, `to = module.network.aws_subnet.private`. Keep the same `count` or `for_each` expression inside the module so every index or key lands where it was.
- A module called with `for_each` needs one block per key per resource: `from = aws_iam_role.svc["api"]`, `to = module.service_role["api"].aws_iam_role.this`. Read the keys from the current map, never guess them.
- Every name-like argument (`bucket`, `identifier`, `name`, `name_prefix`, `cidr_block`) must evaluate to the live value in every caller. If the module builds names from `name_prefix` and `environment`, check the result equals today's literal; if it does not, take the full name as an input instead.
- Each root's output keeps its name and type, now reading `module.<call>.<output>`.

Default chunks

| id | title | outcome |
| --- | --- | --- |
| C1 | module: versions, variables, resources, outputs | no-changes |
| C2 | root: module call, moved.tf, readers re-pointed, old blocks removed | moves-only |
| C3 | tests, README, examples/basic | no-changes |

## dedupe: converge copies across roots onto one module

Inventory

- The copies, side by side: one table row per argument with each root's value. Identical rows become the module body; rows that differ become inputs, and each root passes its own value from its copy. A difference is never resolved by picking one root's value.
- A resource that exists in some roots and not others is a structural difference. Ask whether it stays outside the module in those roots (preferred) or becomes optional inside it.
- Each root's backend key. Every root keeps its own state and moves its own resources into its own module call, so `moved` works per root. Merging resources from several states into one root is not a move: it takes `removed` with `destroy = false` in one root and `import` in the other, changes state, and is out of scope; raise it instead.

Interface and moved map

- As in extract, once per root. The moved map has rows for every root, and moved_coverage runs on every root.

Default chunks

| id | title | outcome |
| --- | --- | --- |
| C1 | module from the common shape | no-changes |
| C2..Cn | one per root: module call with its own values, moved.tf, readers | moves-only |
| last | tests, README, examples/basic | no-changes |

## refactor: rework a module's interface

Inventory

- `describe` on the module and `change_impact` on it for every root that calls it. Every caller in the repository changes in the same run, because a variable rename has no `moved` equivalent: a caller that still passes the old name fails to plan.
- A caller outside the repository (a registry or git consumer) cannot be updated here: list it and say the change needs a major version.

Interface

- Grouping related scalars into one typed `object({...})` uses `optional(type, default)` (Terraform 1.3) only where a default is a documented constant, never for a decision. Add a `validation` where the domain is known; cross-variable references in a validation need Terraform 1.9.
- Every caller passes values that evaluate to exactly what it passes today, so its plan is no-changes.
- An address inside the module that changes gets its `moved` block inside the module itself, because a module may move its own objects; callers then need nothing.

Default chunks

| id | title | outcome |
| --- | --- | --- |
| C1 | module: new variables, body reads them, old variables removed | no-changes |
| C2..Cn | one per caller root: call rewritten to the new interface | no-changes |
| last | tests and README updated | no-changes |

Covers moving root-module resources into reusable modules (moved/removed/import blocks, module layout, variable/output interface, sources, tests); read before extracting, deduplicating or re-shaping a Terraform module.

Doc base: D=https://developer.hashicorp.com/terraform. Citations below use full URLs.

## moved blocks: syntax and versions
- `moved { from = <old address>  to = <new address> }`; both required; addresses may select modules, resources, or resources inside child modules [doc-verified: https://developer.hashicorp.com/terraform/language/block/moved#complete-configuration]
- Before planning, Terraform renames the state object at `from` to `to`, so nothing is destroyed [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#move-a-resource-or-module]
- Requires Terraform v1.1+; older versions use `terraform state mv` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#requirements]
- Cannot turn a managed `resource` into a `data` resource [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#overview]

## moved: root resource into a child module call
```hcl
moved {
  from = aws_vpc.main
  to   = module.network.aws_vpc.this
}
```
- Pattern is documented: `from = aws_instance.example` -> `to = module.ec2_instance.aws_instance.example` (local `./modules/compute`) [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- Split pattern: original module calls new modules and declares `from = aws_instance.a` -> `to = module.x.aws_instance.a` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#split-a-module]
- Write one moved block per resource (or move a whole module call address); every resource in the extracted set needs a mapping or it plans destroy/create [inferred]

## moved: keyed module instances, count <-> for_each
- When a module call gains `count`/`for_each`, map old to an instance: `from = module.a` -> `to = module.a[2]` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#enable-count-or-for_each-for-a-module-call]
- Once either address has an instance key, both are treated as specific instances, so keys can be switched/added/removed [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#enable-count-or-for_each-for-a-module-call]
- count -> for_each on a resource: `from = aws_instance.c[0]` -> `to = aws_instance.c["small"]`, one block per index [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#enable-count-or-for_each-for-a-resource]
- Adding `count` with no moved block: Terraform proposes moving the object to `[0]`, but writing the block explicitly is recommended [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#enable-count-or-for_each-for-a-resource]
- Dedup into a `for_each` module: `from = module.api_role.aws_iam_role.this` -> `to = module.svc["api"].aws_iam_role.this`; keyed addresses quote string keys [inferred from the instance-key rules above]
- Targets inside a registry module may themselves be indexed, e.g. `to = module.web_security_group.aws_security_group.this[0]` [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]

## moved: whole module call, chaining
- Rename a call: `from = module.a` -> `to = module.b`; applies to all instances of the call [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#rename-a-module-call]
- Documented example `from = module.vpc` -> `to = module.learn_vpc` (registry source) [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- Chain renames (`a`->`b`, then `b`->`c`) so configs at any earlier address still upgrade [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#rename-a-resource]

## moved: where the block lives, external sources
- Module references in a moved block resolve relative to the module instance that defines it [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#split-a-module]
- A module may only make moved statements about its own objects and objects of its child modules; so a root->child move belongs in the root (the caller), not in the child [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#split-a-module]
- A moved block inside a child module can only rename that module's own/descendant objects (for module authors shipping a refactor to callers) [inferred]
- Cross-module moves break the "closed box" rule; documented as assuming modules are maintained together and distributed in a single module package [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#split-a-module]
- No documented ban on moving into a registry/git-sourced module: the tutorial moves local-module resources into `terraform-aws-modules/security-group/aws` 4.13.0 [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- That tutorial lists Terraform v1.3+ as prerequisite (`required_version = ">= 1.3.0"`), no reason given [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#prerequisites]
- v1.1-1.2 rejected moves into modules from another module package; v1.3 lifted it, so require >= 1.3 for moves into external-source modules [inferred, NOT found on developer.hashicorp.com]

## moved: keep the blocks
- Removing a moved block is a breaking change: old-address users plan delete instead of move; retain historical blocks (removal only safe for private modules once all users applied) [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#remove-a-move-block]

## Plan output for moves (for hand-off predictions)
- Next plan includes the address update; result is "as if the object had originally been created" at the new address [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/refactoring#move-a-resource-or-module]
- Line format: `# aws_instance.example has moved to module.ec2_instance.aws_instance.example` [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- Moves combined with diffs show `# <new> will be updated in-place` plus `# (moved from <old>)` [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- Pure move ends `Plan: 0 to add, 0 to change, 0 to destroy.`; missing moves show as N to add / N to destroy [doc-verified: https://developer.hashicorp.com/terraform/tutorials/configuration-language/move-config#move-your-resources-into-modules]
- Success criterion for a refactor hand-off: zero add/destroy; any "must be replaced" means an attribute differs between old resource and module body [inferred]

## removed blocks
```hcl
removed {
  from = aws_instance.example
  lifecycle { destroy = false }
}
```
- Available in Terraform v1.7+; earlier use `terraform state rm` [doc-verified: https://developer.hashicorp.com/terraform/language/v1.7.x/resources/syntax#removing-resources]
- `destroy = false` removes from state without destroying; default destroys; `destroy` is the only lifecycle argument allowed [doc-verified: https://developer.hashicorp.com/terraform/language/block/removed#lifecycle]
- In v1.7 docs the `lifecycle` block is required [doc-verified: https://developer.hashicorp.com/terraform/language/v1.7.x/resources/syntax#removing-resources]
- No instance keys in `from` for multi-instance resources [doc-verified: https://developer.hashicorp.com/terraform/language/state/remove#remove-a-resource-from-state]
- Only destroy-time provisioners allowed [doc-verified: https://developer.hashicorp.com/terraform/language/block/removed#provisioner]
- Preferred over `terraform state rm` because the result can be previewed in plan [doc-verified: https://developer.hashicorp.com/terraform/language/state/remove#remove-a-resource-from-state]
- Use `removed` when the object leaves this config/state (handed to another root or team); use `moved` when it stays in the same state at a new address [inferred]
- Dedup across separate roots (separate states) cannot be done with moved: needs `removed {destroy=false}` in one root plus `import` in the other [inferred]
- Whether `from = module.x` is accepted: not confirmed on fetched pages [inferred]

## import blocks (state-changing: a skill must write, never run apply)
- Requires v1.5.0+; processed at plan, imported into state at apply [doc-verified: https://developer.hashicorp.com/terraform/language/v1.5.x/import#syntax]
- Args: `to`, `id` or `identity`, `for_each`, `provider` [doc-verified: https://developer.hashicorp.com/terraform/language/block/import#configuration-model]
- `to` may be a module address, e.g. `module.group[each.value.group].aws_s3_bucket.this[each.value.key]`; must match an existing resource block [doc-verified: https://developer.hashicorp.com/terraform/language/block/import#example]
- `to` pointing at a nonexistent module errors from v1.9 [doc-verified: https://developer.hashicorp.com/terraform/language/v1.9.x/upgrade-guides]
- Place in `imports.tf` or beside the resource; may be kept or deleted after import [doc-verified: https://developer.hashicorp.com/terraform/language/block/import#example]
- Import blocks only allowed in the root module: NOT found in fetched docs [inferred]

## Standard module structure
- Only the root module is required; `README(.md)`, `LICENSE`, `main.tf`, `variables.tf`, `outputs.tf` recommended (even if empty) [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/structure]
- Every variable and output gets a one-to-two-sentence description [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/structure]
- `examples/` at repo root; examples call the module by its external source address, not a relative path [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/structure]
- Nested modules in `modules/`; with README = public, without = internal; call via `./modules/<name>` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/structure]
- Nested modules should be composable by the caller, not call each other [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/structure]

## Providers in modules
- A module meant to be called by others must not contain `provider` blocks; child inherits default provider configs [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/providers]
- Modules with own provider configs are incompatible with `for_each`, `count`, `depends_on` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/providers#legacy-shared-modules-with-provider-configurations]
- Aliased providers: declare in `required_providers` with `configuration_aliases`, caller passes `providers = {...}` [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/providers#provider-aliases-within-modules]
```hcl
terraform { required_providers { aws = { source = "hashicorp/aws", configuration_aliases = [aws.dst] } } }
```
- Extraction step: move `provider` blocks out of the extracted code and keep them in the root [inferred]

## When to write a module, composition
- Use modules in moderation; a good module raises a new architectural concept from several resources [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop#when-to-write-a-module]
- Avoid thin wrappers around one resource type; if you can't name it differently from the main resource, use the resource directly [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop#when-to-write-a-module]
- Keep the tree flat (one level of child modules), prefer composition [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/composition]
- Dependency inversion: pass dependencies in (`vpc_id`, `subnet_ids`) rather than creating them; keep modules small [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/composition#dependency-inversion]
- No "create if missing" logic; accept the object as input and let the caller create or look it up; type the input to only the attributes needed [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/composition#conditional-creation-of-objects]
- Data-only modules only when they raise abstraction [doc-verified: https://developer.hashicorp.com/terraform/language/modules/develop/composition#data-only-modules]

## Input variables
- Unset `type` means `any`; `any` is rarely correct, use only for pass-through (e.g. `jsonencode`) [doc-verified: https://developer.hashicorp.com/terraform/language/expressions/type-constraints#dynamic-types-the-any-constraint]
- `optional(type, default)` in object types; omitted default = typed null; defaults apply top-down in nested types [doc-verified: https://developer.hashicorp.com/terraform/language/expressions/type-constraints#optional-object-type-attributes]
- `optional` stable since v1.3.0; modules for older Terraform must not use it [doc-verified: https://developer.hashicorp.com/terraform/language/v1.3.x/upgrade-guides#optional-object-type-attributes]
```hcl
variable "svc" { type = map(object({ port = number, public = optional(bool, false) })) }
```
- `validation` (v0.13+) needs `condition` and `error_message` [doc-verified: https://developer.hashicorp.com/terraform/language/expressions/custom-conditions#input-variable-validation]
- Before v1.9.0 validation could reference only the variable itself; v1.9+ may reference other variables [doc-verified: https://developer.hashicorp.com/terraform/language/v1.9.x/expressions/custom-conditions#input-variable-validation]
- `nullable` default `true`; `false` guarantees non-null inside the module (v1.1+) [doc-verified: https://developer.hashicorp.com/terraform/language/v1.9.x/values/variables#disallowing-null-input-values]
- `sensitive` hides in CLI output but value still stored in state [doc-verified: https://developer.hashicorp.com/terraform/language/block/variable#sensitive]
- `ephemeral` (v1.10+) omits from state/plan; usable in ephemeral outputs, provider blocks, write-only args; taints referencing exprs [doc-verified: https://developer.hashicorp.com/terraform/language/block/variable#ephemeral]
- Interface refactor = caller-breaking; renaming a variable has no moved equivalent, so bump major version [inferred]

## Outputs
- `description`, `sensitive` (still in state), `depends_on` [doc-verified: https://developer.hashicorp.com/terraform/language/block/output]
- `precondition` validates an output before exposure (v1.2.0+) [doc-verified: https://developer.hashicorp.com/terraform/language/expressions/custom-conditions#preconditions-and-postconditions]
- `ephemeral` outputs: v1.10+, child modules only [doc-verified: https://developer.hashicorp.com/terraform/language/block/output#ephemeral]
- After extraction, root references change to `module.<name>.<output>`; expose every attribute the root previously referenced [inferred]

## Sources and versions
- Local paths start `./` or `../`; local sources do not support `version` [doc-verified: https://developer.hashicorp.com/terraform/language/block/module#source]
- `version` only when source is a registry module [doc-verified: https://developer.hashicorp.com/terraform/language/block/module#version]
- Git: `?ref=` accepts any `git checkout` value (branch, tag, SHA); default branch if omitted [doc-verified: https://developer.hashicorp.com/terraform/language/modules/sources]

## terraform test
- Files `.tftest.hcl`/`.tftest.json`; available v1.6.0+ [doc-verified: https://developer.hashicorp.com/terraform/language/tests]
- Default test dir `tests/`; root-dir test files also load; `-filter=tests/x.tftest.hcl` [doc-verified: https://developer.hashicorp.com/terraform/cli/commands/test]
- `run` defaults to `command = apply` (real infra); `command = plan` creates nothing [doc-verified: https://developer.hashicorp.com/terraform/language/tests#run-blocks]
- File-level `variables` apply to all runs; run-level overrides [doc-verified: https://developer.hashicorp.com/terraform/language/tests#variables]
- `expect_failures = [var.x]` tests validations; failures expected only in the run's command [doc-verified: https://developer.hashicorp.com/terraform/language/tests#expecting-failures]
- `mock_provider` v1.7.0+; `mock_resource`/`mock_data` take `defaults`; `override_resource` skips provider; same-type real+mock needs `alias` [doc-verified: https://developer.hashicorp.com/terraform/language/tests/mocking]
```hcl
mock_provider "aws" {}
run "rejects_bad_port" {
  command         = plan
  variables       { port = 0 }
  expect_failures = [var.port]
}
```

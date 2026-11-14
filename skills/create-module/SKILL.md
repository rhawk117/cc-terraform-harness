---
name: create-module
description: >-
  Build a reusable Terraform module, or turn existing Terraform into one,
  without destroying a single resource: inventory the code, design a typed
  interface, write MODULE-PLAN.md with a moved block for every address and
  the expected plan for every caller, then hand each chunk to
  terraform-author and check it. Four modes: new (a module from a
  description), extract (lift resources out of a root into a module call),
  dedupe (converge copies across environments or roots onto one module)
  and refactor (rework a module's variables and outputs while every caller
  plans clean).
when_to_use: >-
  Requests such as "write a reusable module for an upload bucket", "pull
  the VPC and subnets out of envs/prod into a network module", "dev and
  prod copy the same queue setup, make it one module", "extract the
  per-service IAM roles into a module", "change modules/app-db to take one
  object variable", "modularize this", "DRY up these environments". Not
  for adding or editing resources inside an existing module
  (writing-terraform), reviewing (review-module) or only running checks
  (check-module).
argument-hint: "[new|extract|dedupe|refactor] [path]"
arguments: [mode, path]
paths:
  - "**/*.tf"
  - "**/*.tfvars"
  - "**/*.tftest.hcl"
allowed-tools:
  - mcp__plugin_terraform-harness_terraform__describe
  - mcp__plugin_terraform-harness_terraform__change_impact
  - mcp__plugin_terraform-harness_terraform__provider_schema
  - mcp__plugin_terraform-harness_terraform__plan_digest
  - mcp__plugin_terraform-harness_terraform__diagnostics
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
  - Bash(python3 ${CLAUDE_PLUGIN_ROOT}/skills/writing-terraform/scripts/*)
---

# Create a Terraform module

A module is done when every caller plans exactly what MODULE-PLAN.md said it would, usually 0 to destroy, and the module could be called by a root that does not exist yet. You plan; terraform-author writes. Every HCL line follows the writing-terraform skill, so this skill adds the module-level decisions it does not make: the boundary, the interface, the moved map, the order of the work and the gates between chunks.

## Standing rules

These hold from the first read to the hand-off.

1. **No HCL before an approved plan.** Nothing under the module or a caller root changes until MODULE-PLAN.md passes `validate_plan.py --require-approved`. Approval comes from the user through AskUserQuestion. When you cannot ask (a headless run), the prompt's explicit go-ahead counts, recorded as `approved_by: prompt`; without one, stop after writing the plan.
2. **State never moves by accident.** Every resource or module address that leaves a root gets a `moved` block in that root's `moved.tf`, because a module can only move its own objects and the caller owns the state. A module called with `for_each` takes one block per key per resource. A chunk is not done until `moved_coverage.py` is clean for every root it touched. Keep the blocks after apply; deleting one later turns the move back into a destroy for anyone who has not applied.
3. **Live identity is kept.** A name-like argument (`bucket`, `identifier`, `name`, `cidr_block`) must evaluate in each caller to the value it has today. If a naming scheme in the module would change one, the caller passes the full live value instead. A change that would replace a stateful resource (writing-terraform rule 06) stops the run and goes to the user.
4. **The interface is what differs between callers.** Values that differ, or that are decisions (sizing, retention, CIDRs), are required variables with a type and a description and no default. Dependencies come in as inputs (`vpc_id`, `kms_key_arn`) instead of being created or looked up inside. Every attribute a caller reads today becomes an output.
5. **A module is reusable on its own.** No `provider`, `backend` or `cloud` block; `required_providers` with a version constraint; `required_version` at least the newest feature used (`moved` 1.1, `optional()` 1.3, `terraform test` 1.6, `mock_provider` and `removed` 1.7, cross-variable validation 1.9); a README; tests with `command = plan`. `module_lint.py` checks these.
6. **You never change real infrastructure or state.** No `apply`, `import`, `state` subcommand, `taint`, or `plan` against a real backend. You hand the plan commands to the user.

## Arguments

`$mode` is `new`, `extract`, `dedupe` or `refactor`; `$path` is the module or root it starts from. When either is missing, infer it (a directory with callers is refactor, a root with the resources is extract, several roots with the same blocks is dedupe, nothing yet is new) and confirm it with AskUserQuestion along with the other open questions in step 2.

## Procedure

Scripts used below (scripts/validate_plan.py checks MODULE-PLAN.md, scripts/module_lint.py checks the module is reusable, scripts/moved_coverage.py checks every removed address has a move), each printing `path:line: CODE message` and exiting 0 when clean, 1 on findings and 2 on a usage error:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/validate_plan.py MODULE-PLAN.md [--require-approved]
python3 ${CLAUDE_SKILL_DIR}/scripts/module_lint.py MODULE_DIR
python3 ${CLAUDE_SKILL_DIR}/scripts/moved_coverage.py --base REF ROOT [ROOT ...]
python3 ${CLAUDE_PLUGIN_ROOT}/skills/writing-terraform/scripts/smell_grep.py DIR [DIR ...]
```

If `python3` is not available, do each script's check by hand from its docstring and say so in the hand-off.

### 1. Inventory

Read the section of `references/modes.md` for the mode, and follow its inventory list. In every mode:

- Record the base ref: `git rev-parse HEAD`. moved_coverage compares against it, so uncommitted changes in the source roots must be committed or stashed first; ask when there are any.
- Call `describe` on each source root and on the module if it exists; `change_impact` on an existing module for its callers.
- Read each root's `.terraform.lock.hcl` and `required_version`, so the module's constraints admit what the callers already lock.
- Find every reader of every address that will move (`LSP` `findReferences`, or `rg` when terraform-ls is absent).

### 2. Design

Draft the interface and the moved map following the mode's section. Check the doc-verified facts in `references/module-refactoring.md` before writing any `moved`, `removed` or `optional()` construct you have not used in this repository. Collect every decision you could not source (a value no caller states, a structural difference between roots, a thin single-resource module) and ask them in one AskUserQuestion call; in a headless run take the safe choice (a required variable, the resource left outside the module) and list it under open questions.

### 3. Write and approve the plan

Copy assets/MODULE-PLAN.template.md (`${CLAUDE_SKILL_DIR}/assets/MODULE-PLAN.template.md`) to `MODULE-PLAN.md` at the repository root and fill it: inventory, interface, moved map, chunks from the mode's default table, and one expected-plan line per caller. A chunk's outcome is the plan of the root it touches; a chunk that touches only the module is `no-changes`. Run `validate_plan.py` and fix every finding.

Then ask once with AskUserQuestion: approve, edit (say what), or stop. On approve set `status: approved` and `approved_by: user`, and run `validate_plan.py --require-approved`.

### 4. Build, one chunk at a time

For each chunk in order:

1. Set its status to `in-progress` and fill assets/author-dispatch.template.md (`${CLAUDE_SKILL_DIR}/assets/author-dispatch.template.md`) from the plan: owned files, change, interface rows, moved rows, live values, outcome. Dispatch the terraform-author subagent with it. One author at a time, because each chunk builds on the last.
2. When it reports done, read its diff, then run the gate on what the chunk touched: `diagnostics` on the module and on each caller root it changed; `module_lint.py` on the module; `moved_coverage.py --base REF` on each caller root it changed; `smell_grep.py` on every directory it changed. A module-only chunk in refactor mode leaves callers broken until their chunk lands, so check callers at their own chunk.
3. Clean gate: set the chunk to `done`. Failed gate: dispatch the author once more with the exact failing output. If it fails again, set the chunk to `failed` and ask with AskUserQuestion: fix it by hand, revise the plan, or stop. Never edit a check or a moved block just to make the gate pass.

When every chunk is done, call `change_impact` on the module and confirm that every root it reports is in `callers` with an expected-plan line. Set `status: done`.

### 5. Hand off

End with these sections, in this order:

- **Module**: the path, what it manages, its inputs and outputs.
- **Changed**: each file and what the change in it does.
- **Expected plan**: per caller root, one line per address (move from and to, create, update), then "N to add, N to change, N to destroy". A refactor states "no changes" per root outright.
- **Required inputs**: variables with no default and who supplies each.
- **Assumptions and open questions**: every decision made without the user.
- **Not verified**: anything a gate could not check, such as a schema lookup that failed or a plan never run.
- **Next**: in each caller root, `terraform plan -out=tfplan` and the explain-plan skill on it; apply only when the plan matches. Keep each `moved.tf` after apply. MODULE-PLAN.md holds the moved map and can be deleted once every root has applied.

## References

- `references/modes.md`: inventory, interface, moved-map and chunk steps for each mode. Read the one section for the mode in use.
- `references/module-refactoring.md`: HashiCorp-cited facts on `moved`, `removed`, `import`, module layout, variable types, sources and `terraform test`, each marked doc-verified or inferred. Treat an inferred line as a lead, not a fact.
- `${CLAUDE_PLUGIN_ROOT}/skills/writing-terraform/SKILL.md`: the HCL rules terraform-author follows; its module skeleton (path in the new section of `references/modes.md`) is the starting point for a new module, and `assets/examples-basic/main.tf` here is the example caller.

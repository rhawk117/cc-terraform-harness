---
name: onboard-toolchain
allowed-tools: mcp__plugin_terraform-harness_terraform__describe mcp__plugin_terraform-harness_terraform__diagnostics mcp__plugin_terraform-harness_terraform__plan_digest
description: >-
  Bootstrap or improve the tooling around any Terraform repository through a short interview: version pinning,
  fmt/validate, tflint, trivy or checkov, OPA/conftest policy, terraform-docs, pre-commit, a local
  task runner, CI integration, dependency automation, and repo hygiene, with tool versions resolved from GitHub
  releases and every existing rule, hook, ignore, and workflow step preserved. Use this whenever the user wants to
  set up, audit, harden, modernize, or add standard tooling to a Terraform repo, asks what linting or scanning a
  repo is missing, wants pre-commit or CI checks for Terraform, wants tool versions pinned or updated, or mentions
  tflint, trivy, tfsec, checkov, conftest, terraform-docs, pre-commit-terraform, or infracost for a repo. Also use
  it for "clean up this terraform repo" or "make this repo production ready" when .tf files exist. If nothing is
  missing, it reports that it found no room for improvement instead of inventing work.
---

<purpose>
Take a Terraform repository from whatever state it is in to a coherent, pinned, verified toolchain, driven by the user's answers rather than assumptions. The skill improves what exists; it never replaces a working setup with a different one of equal value. When discovery and the interview turn up nothing to add, the correct output is the single sentence in `<no-change-outcome>`.

Two facts shape every decision here:

- A repository that deploys environments (root modules) needs state, auth, plan gating, policy, and drift far more than it needs docs generation or release automation. A repository that publishes modules needs the reverse. Ask which one this is before proposing anything.
- The user's existing rules are the product of decisions you were not part of. A custom tflint rule, a disabled check, a `.trivyignore` entry, or a hand-written workflow step is evidence of intent. Extend around it; do not overwrite it.

</purpose>

<tool-contract>
Use `describe` with a module directory, `.tf` file, or `.tfvars` file before
reading Terraform configuration. The path is relative to the project root or
absolute inside it. A module-directory
response merges `files`, `data_sources`, `modules`, `resources`, `variables`,
and `outputs` at the top level and carries backend, providers, module calls,
and declaration details in `module`; file and tfvars responses carry their
references or assignments in `file` and `tfvars`. Use `diagnostics` on a
module directory after an approved tooling change to check `fmt`, `validate`,
and `tflint`. Use `plan_digest` with argument `path` only for an existing JSON
plan inside the project root; it reports status, changes, moves, imports,
removals, and risk flags without running a plan. These tools do not initialize
Terraform or change infrastructure.

</tool-contract>

<workflow>
Run these phases in order. Do not skip the interview because discovery looks conclusive; discovery tells you what files exist, not why.

## Phase 1: Discover

Read every relevant configuration file before asking questions: `.pre-commit-config.yaml`, `.tflint.hcl`, `trivy.yaml`, `.trivyignore`, `.checkov.yaml`, `policy/*.rego`, every CI definition, `renovate.json`, `Makefile` or task runner. Record each custom rule, disabled check, ignore entry, pinned version, and named workflow step as the preservation manifest for Phase 5. Read `references/toolchain.md` for what each layer means and what "configured" looks like.

## Phase 2: Interview

Ask the questions in `references/interview.md`, skipping any the discovery already answered. Ask in small batches (three to five questions) and wait for answers before continuing. If the runtime offers a structured question or choice tool, use it; otherwise ask in plain chat. Never proceed on a guess where a question would resolve it; the user would rather answer than discover a silent assumption later.

Minimum information before Phase 3:

1. Repo type: root-module (deploys environments), module (published for reuse), or mixed.
2. Cloud provider(s) and CI platform.
3. Which gaps from Phase 1 the user wants closed, and which they deliberately leave open.
4. Any tool the user forbids or requires (for example, the org mandates checkov, or trivy is blocked by network policy).
5. Which tool versions the user requires, or whether existing pins should remain unchanged.

## Phase 3: Propose

Produce a change plan as a table before touching any file:

| Layer | Change | Action | Preserves | Why |
| ----- | ------ | ------ | --------- | --- |

`Action` is one of `add`, `extend`, `pin`, `replace-deprecated`, or `skip`. `Preserves` names the existing rule, hook, ignore, or step the change keeps intact. `Why` ties the change to a user answer or a discovery finding, never to a generic best practice alone.

If the table has no rows with an action other than `skip`, go straight to `<no-change-outcome>`.

Otherwise, present the table and wait for approval. The user may strike rows.

## Phase 4: Resolve versions

Use the versions recorded in repository configuration as the starting point.
Do not invent or silently update pins; ask the user for any version that is
missing or needs to change. Apply the compatibility rules in
`references/toolchain.md` under "Version compatibility": the Terraform version
must satisfy the repo's existing `required_version`; the tflint ruleset must
be compatible with the pinned tflint per the ruleset's README; the
`pre-commit-terraform` rev must be one whose hooks match the binaries you are
pinning.

Record every version in one place (`aqua.yaml`, `mise.toml`, or `.tool-versions`; `.terraform-version` for Terraform itself) and reference that place from CI and the task runner. A version that appears in two files will drift.

## Phase 5: Implement

Work through the approved table one row at a time. For each row:

- Read the target file again immediately before editing it.
- Merge, do not replace. Follow `<preservation-rules>`.
- Use the snippets in `references/configs.md` as starting points, adapted to the repo's paths and the user's answers.
- For CI, follow `references/ci-integration.md`. Add named steps into the existing jobs; do not create a parallel workflow that duplicates an existing one.
- Add or extend the task runner so every read-only command CI runs has a local equivalent with the same flags.
- Add or extend the agent instruction file (`AGENTS.md` or the repo's existing equivalent) with the local commands and the gates that must pass before commit.

## Phase 6: Verify

You are not done when the files are written. Run the check-module skill on each affected module and carry its per-check results, skipped checks included, into the Phase 7 report.

Then reread the configuration files and compare them with the preservation manifest from Phase 1.

For CI files you cannot execute, at minimum parse them (`python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' <file>` if PyYAML is present, otherwise a careful read) and confirm every step you added has a `name:` and every step that existed before still exists with its original name and content.

## Phase 7: Report

Finish with:

1. What changed, per file, one line each.
2. What was preserved and where (the manifest from Phase 1, each item marked kept).
3. Verification results, including anything skipped and why.
4. Follow-ups the user must do outside the repo (create the OIDC role, add a branch protection rule, grant the token scope).

</workflow>

<side-effect-boundary>
This skill configures tooling; it never touches infrastructure. In every phase:

- Never run `terraform apply`, `terraform destroy`, `terraform import`, `terraform state`, `terraform taint`, `terraform untaint`, `terraform test`, `terraform force-unlock`, or any orchestrator wrapper of those.
- Never run `terraform init` against a real backend or `terraform plan` against a real backend. Local verification uses `terraform init -backend=false`; a plan is only ever consumed as a `plan.json` the user already produced.
- Never add an apply, destroy, or resource-creating test step to any CI definition. Existing apply steps are preserved untouched under `<preservation-rules>`; the skill neither adds, removes, nor edits them.
- Never propose end-to-end tests, idempotency applies, or anything that needs a live account. If the user asks for those, say they are out of this skill's scope and stop at the boundary.
- Scanners and policy in CI run against plan JSON that the repo's existing plan step produces. If no plan step exists, the scan and policy steps run against the HCL directory and the report says why.

</side-effect-boundary>

<preservation-rules>
These hold for every edit in Phase 5.

- Never delete an existing pre-commit hook, tflint rule block, `.trivyignore` or `.checkov.yaml` skip, Rego file, workflow step, `.gitignore` line, or task-runner target. Add beside it.
- When an existing configuration disables a check, keep it disabled. If you think it should be enabled, say so in the report; do not flip it.
- When an existing version pin is older than the resolved latest, ask before bumping. Bumping is a separate change with its own row in the plan.
- When an existing workflow step lacks a `name:`, add one that describes what the step already does. Do not change the `uses:` or `run:` content while doing so.
- When a `tfsec` reference exists, propose `replace-deprecated` with `trivy config`, carry every `tfsec:ignore` comment over as the equivalent trivy ignore, and show the mapping in the plan. This is the only case where removal is the right action, and it still requires approval.
- When the repo uses an orchestrator (terragrunt, terramate, atmos, atlantis), route commands through it rather than calling `terraform` directly, and keep its config untouched unless a row in the plan targets it.
- If a change cannot be made without breaking an existing rule, stop and ask. State which rule conflicts and what the two resolutions are.

</preservation-rules>

<no-change-outcome>
When discovery reports zero gaps and the interview surfaces no user-requested change, respond with exactly:

> I could not find any room for improvement in this repository's Terraform toolchain.

Follow it with the discovery table so the user can see what was checked, and nothing else. Do not propose optional layers the user did not ask for, do not bump versions unprompted, and do not restyle existing configuration.

</no-change-outcome>

<verification-discipline>
Everything you assert about the repo must trace to a file you read or a command you ran in this session. Everything you assert about a tool version must trace to the resolver output or a user answer. When neither exists, the honest sentence is "I have not verified this" followed by the command that would.

Before writing any configuration, confirm the target tool's current CLI flags from its `--help` output or bundled reference; several of these tools renamed flags across releases. Do not rely on the flag names you remember.

</verification-discipline>

<references>
- `references/toolchain.md`: the layer model, what "present" means per layer, version compatibility rules, and the root-vs-module minimum sets. Read during Phase 1 and Phase 4.
- `references/interview.md`: question bank with skip conditions and how each answer changes the plan. Read during Phase 2.
- `references/ci-integration.md`: how to add steps to GitHub Actions, GitLab CI, Azure Pipelines, and generic runners without disturbing existing jobs; OIDC patterns; plan-on-PR and apply-on-merge shapes. Read during Phase 5 for any CI row.
- `references/configs.md`: starting snippets for pre-commit, tflint, trivy, conftest layout, renovate, aqua/mise, task runner targets, and AGENTS.md. Read during Phase 5.

</references>

# Interview question bank

Ask in batches of three to five. Skip any question whose "skip when" condition is met by discovery output or by an earlier answer. Each question lists how the answer changes the plan so you can explain the why in the proposal table.

## Batch 1: Shape

**Q1. Is this repository a root-module repo (it deploys environments), a module repo (it publishes reusable modules), or mixed?**
Skip when: discovery found a remote backend and no `examples/` directory (root), or found `examples/` with no backend (module), and you state the inference and the user does not correct it.
Effect: selects the minimum set from `toolchain.md`; decides whether terraform-docs and release automation are rows or skips; decides whether a missing backend is a gap.

**Q2. Which cloud provider(s) does it target?**
Skip when: `required_providers` or provider blocks make it unambiguous.
Effect: selects the tflint ruleset(s) to pin, the OIDC pattern, and the trivy/checkov check families that matter.

**Q3. Which CI platform runs this repo, and is there a workflow or pipeline you consider the canonical one?**
Skip when: exactly one CI definition was found.
Effect: selects the `ci-integration.md` section; identifies the job to extend rather than duplicate.

**Q4. Do you use an orchestrator (terragrunt, terramate, atmos, atlantis) or an execution platform (HCP Terraform, Spacelift, env0, Scalr, Digger)?**
Skip when: discovery found the config file and the user confirms it is in use.
Effect: every command in CI and the task runner routes through the orchestrator; execution platforms may already cover plan and drift, in which case those rows become skips with a note.

## Batch 2: Scope

**Q5. Here are the gaps discovery found. Which do you want closed, and which are deliberate?**
Present the discovery table. Never skip this question when gaps exist.
Effect: rows the user marks deliberate become `skip` with the reason "user decision"; everything else proceeds.

**Q6. Are any tools mandated or forbidden by your organization?** (Examples: must use checkov; trivy blocked because runners cannot reach its checks bundle; OPA policies must come from a central repo.)
Skip when: the user already named the scanner or policy source.
Effect: substitutes tools; may turn the policy row into "reference the central policy bundle" instead of "create policy/".

**Q7. For existing tool pins that are behind the latest release, do you want them bumped in this change, or left alone?**
Skip when: discovery found no pinned versions.
Effect: creates or omits `pin` rows for existing tools. Bumps are never silent.

**Q8. Should security scanning and policy run against plan JSON in CI (requires plan credentials on PRs), against the HCL only, or both?**
Skip when: CI already scans plan JSON.
Effect: decides whether the CI change needs a plan step with OIDC before the scan steps.

## Batch 3: Versions and environment

**Q9. Which tool versions should the approved plan use?**
Skip when: the repository pins every tool in scope and no updates are approved.
Effect: ask the user to supply versions for every new or changing tool and record them as user-provided in the report.

**Q10. How are tool versions managed on developer machines today: aqua, mise, asdf, tenv/tfenv, Homebrew, or nothing?**
Skip when: discovery found `aqua.yaml`, `mise.toml`, or `.tool-versions`.
Effect: selects the single file where versions live; if "nothing", propose one and explain that CI will read the same file.

**Q11. What is the local entry point developers use today: make, task, just, scripts, or nothing?**
Skip when: discovery found a task runner file.
Effect: extend the existing runner rather than adding a second one.

## Batch 4: CI specifics (root repos only)

**Q12. How does CI authenticate to the cloud today, and is there an OIDC identity provider and role already set up?**
Skip when: discovery found `id-token: write` plus a role assumption step and no static credential markers.
Effect: if static keys are in use, the plan includes a `replace` row for the auth step plus a follow-up for the user to create the OIDC trust; you cannot create cloud IAM resources from inside the repo.

**Q13. Should plan run on every PR with its output posted as a comment?**
Skip when: CI already does this and the user did not flag it.
Effect: shapes the plan job. Apply is never added by this skill; if the user asks for it, note it as out of scope.

**Q14. Do you want a scheduled drift plan, and if so how often and where should the alert go?**
Skip when: a scheduled plan exists.
Effect: adds the schedule trigger and a failure-on-diff step; the alert destination decides whether a notification step is needed or a failed run is enough.

## Batch 5: Module repos only

**Q15. Are versions released by hand today, or from commit history (release-please, semantic-release)?**
Skip when: discovery found release tooling.
Effect: adds or skips the release automation row, and the PR title lint that makes it trustworthy.

**Q16. Should every directory under examples/ be planned in CI?**
Skip when: CI already plans examples.
Effect: adds the example matrix job using `terraform init -backend=false` and `terraform plan` with mock or default variables; nothing is applied.

## Closing question

**Q17. Anything in this repo I should not touch?**
Never skip. Effect: adds to the preservation manifest.

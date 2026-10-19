---
name: explain-plan
allowed-tools: mcp__plugin_terraform-harness_terraform__plan_digest
description: >-
  Explain a Terraform plan in plain language that cuts straight to what matters - verdict first, then what changes, then what could hurt. Use this whenever the user pastes or points at plan output (`terraform show -json plan.out`, a plan JSON export, or a plan file that can be rendered that way) and wants to know what it will do, whether it is safe to apply, what will be destroyed or replaced, or a summary for a reviewer or non-Terraform stakeholder. Trigger even when they just say "what does this do", "is this safe", "summarize this plan", or "tl;dr this" with a plan in front of them. Do not use for writing or refactoring Terraform code, state surgery, or provider errors that are not plan output.
---

# Terraform plan explainer

A plan is the only honest preview of what `apply` will do, and almost nobody reads the whole thing. Reviewers skim for the `Plan:` line, miss the one `# forces replacement` buried in 400 lines of tag diffs, and find out about the database rebuild during the maintenance window. This skill exists to make the one paragraph that matters impossible to miss.

The reader might be the SRE approving the apply, the engineer who wrote the change, or a manager who has never seen HCL. Write so the first two lines serve all three and the rest rewards whoever keeps reading.

## Workflow

1. Get the plan as JSON in a file inside the project root. `plan_digest` reads only `terraform show -json` output and refuses any path outside the project root, so a file under `/tmp` cannot be digested. If the user has a binary plan file (`plan.out`, `tfplan`), render it with `terraform show -json plan.out > plan.json` in the module directory. If they pasted JSON, write it to a file in the project. Plan text is not supported: when that is all you have, ask for the plan file or the JSON rendering, and do not guess values from text.

2. Call the `plan_digest` tool with `path` set to the JSON file. It does the counting so you don't miscount by eye.

   The result carries `counts` per action, every changed resource in `resource_changes` with its `actions`, the attributes that forced a replacement (`forced_by`), the names of its `sensitive_attributes` and its `flags`, the `output_changes`, and the top level `moves`, `imports`, `drifted` addresses and `plan_flags` (`mass-destroy`, `drift`, `unsupported-action`). The flags are described in `references/risk-heuristics.md`. Trust its counts over your own reading of the plan. A refused path or an unreadable document is the first line of your explanation, not a footnote.

3. Read the digest, then read the plan itself for anything it flagged. The tool finds the risk; you explain it. For a large plan, dispatch one `terraform-researcher` per flagged resource or per module address in parallel, each asked what the plan says about that address and what in the configuration explains it; they are cheap and disposable, and their reports give you the before/after facts and the declaring file without pulling the whole plan into your context.

4. Check what the plan does besides create, update and destroy. `moves` are renames in state with no infrastructure change, unless `with_change` says the resource also changes. `imports` bring existing resources under management, and `drifted` lists resources someone changed outside Terraform, which the plan may be reverting. Say each in one line.

5. Write the explanation in the format below.

## Output format

Lead with the worst thing. If the plan is boring, say so in one line and stop early. Length scales with risk, not with the number of resources.

```markdown
**Verdict:** <one sentence: safe to apply / needs a look / do not apply as-is, plus the counts that matter>

**What it does**
- 2-6 bullets, grouped by intent, not by resource. "Adds a read replica for the orders database in us-west-2", not "creates aws_db_instance.orders_replica".
- Collapse noise into one bullet: "Tag and description updates on 14 resources, no behavior change."

**Watch out**  (omit the section entirely when there is nothing here)
- Destroys, replacements and what forced them, downtime, data loss, public exposure, IAM widening, cost jumps. One bullet each, concrete: "`aws_db_instance.main` is replaced because `engine_version` changed 14 -> 16. Replacement is delete-then-create: the database is gone until the new one is up, and the data goes with it unless a snapshot exists."

**Details**  (only when the reader wants them, or the plan has more than ~10 changes; wrap in <details> for PR comments)
| Resource | Action | Why |
```

Verdict wording:

- **Safe to apply** - creates and in-place updates only, nothing in the watch-out list.
- **Needs a look** - replacements, destroys of stateless things, security-adjacent changes, or anything the digest flagged.
- **Do not apply as-is** - destroys or replaces a stateful resource without evidence of a backup, opens something to the internet, strips deletion protection, or the plan destroys a large share of the workspace.

## Writing rules and why

- Translate resource types into what they are. `aws_db_instance` is a database, `google_compute_firewall` is a firewall rule, `kubernetes_deployment` is a running workload. The manager does not know the type names and the SRE does not need them repeated.
- Name the attribute that forced a replacement and the direction of the change. "Replaced" alone is useless; "replaced because `subnet_id` changed" tells the engineer whether that was intended.
- Distinguish delete-then-create from create-before-destroy. One is an outage window, the other usually is not. The digest tells you which (`replace-delete-first` or `replace-create-first`).
- Say what is lost. Destroying a bucket, database, queue, disk, KMS key or secret loses data or the ability to decrypt it. Say that plainly instead of "resource will be destroyed".
- Do not narrate every resource. If 30 security group rules are being recreated because a module was refactored, that is one bullet: "The module refactor recreates all 30 ingress rules; brief window where rules are absent."
- Do not hedge with "may" and "could" when the plan is definite. The plan says what will happen. Uncertainty only belongs where Terraform itself says `(known after apply)`.
- No praise, no preamble, no "Here's a breakdown of your plan". Start with the verdict.
- When the plan is clean, the whole explanation can be three lines. Padding a safe plan to look thorough trains readers to skim, which is the problem this skill exists to fix.
- Never invent values the plan does not contain. Sensitive attributes appear in the digest by name only; say that they changed, not what they changed to.

## Reading the digest

`references/risk-heuristics.md` lists the resource-type patterns and attribute patterns `plan_digest` flags and explains why each matters. Read it when a flag fires that you don't immediately understand, or when a plan contains a provider the heuristics don't cover and you need to judge stateful-vs-stateless yourself.

The heuristics are deliberately conservative: a flag means "look here", not "this is wrong". Downgrade a flag in your explanation when the plan itself shows it is fine (for example a destroy of an `aws_s3_bucket` whose `force_destroy` is false will fail rather than lose data, and a `create_before_destroy` replacement of a stateless resource is routine).

## Examples

**Boring plan, engineer asked "what does this do":**

> **Verdict:** Safe to apply. 3 in-place updates, nothing destroyed or replaced.
>
> **What it does**
>
> - Bumps the `api` ECS service from 2 to 4 tasks and raises its CPU reservation.
> - Tag updates on the ALB and target group, no behavior change.

**Dangerous plan, SRE asked "is this safe":**

> **Verdict:** Do not apply as-is. 1 replacement of a production database and 1 security group opened to the internet, alongside 6 routine updates.
>
> **What it does**
>
> - Upgrades the main Postgres database from engine 14 to 16 and moves it to the new private subnets.
> - Opens port 5432 on the database security group to `0.0.0.0/0`.
> - Adjusts autoscaling limits and tags on the app tier.
>
> **Watch out**
>
> - `aws_db_instance.main` is replaced because `subnet_group_name` changed; the engine bump alone would have been in-place. Replacement is delete-then-create, so the database and its data are gone until the new instance finishes, and the plan shows no snapshot. Confirm a snapshot exists or set `skip_final_snapshot = false` first.
> - Ingress rule on `aws_security_group.db` changes from the app subnet CIDR to `0.0.0.0/0` on 5432. That exposes the database to the internet. Almost certainly a mistake.

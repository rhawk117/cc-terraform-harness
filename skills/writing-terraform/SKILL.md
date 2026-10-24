---
name: writing-terraform
description: >-
  Write or change Terraform so the plan does exactly what was asked and
  nothing else: every argument checked against the locked provider schema,
  every value traced to a reference, a variable or the user, data stores
  hardened and protected by default, a moved block for every address change,
  replace-forcing changes to stateful resources stopped and raised, and the
  expected plan handed back. Use when creating or editing .tf, .tfvars or
  .tftest.hcl files: adding a resource or module, renaming a resource,
  switching count to for_each, fixing an AccessDenied or a validate error, or
  changing a database, bucket, table, queue or key.
when_to_use: >-
  Requests such as "add an S3 bucket for the logs", "create a Postgres RDS
  instance", "rename aws_db_instance.main", "convert this count to for_each",
  "the role gets AccessDenied on DynamoDB", "fix this validate error", "write a
  module for", "change the table name". Not for reviewing or grading existing
  Terraform (review-module), explaining a plan (explain-plan) or only running
  fmt, validate and tflint (check-module).
user-invocable: false
paths:
  - "**/*.tf"
  - "**/*.tfvars"
  - "**/*.tftest.hcl"
allowed-tools:
  - mcp__plugin_terraform-harness_terraform__provider_schema
  - mcp__plugin_terraform-harness_terraform__describe
  - mcp__plugin_terraform-harness_terraform__change_impact
  - Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# Writing Terraform

The plan is the deliverable, not the HCL. Code that reads as idiomatic but plans a destroy, invents an instance size or widens IAM to `*` is worse than no code, because the reviewer reads the HCL and the apply does what the plan says. Each rule below names the review-module rubric ID it prevents, so a reviewer's finding and the rule you broke are the same thing. `references/good-vs-bad.md` pairs bad and good HCL for each rule.

## Standing rules

These hold for the whole task, after the first edit as much as before it.

01. **Arguments come from the locked schema (VE7).** Before you write or change a resource or data source block, call `provider_schema` for its type, even a type you know well. An argument the schema does not list does not exist in this provider version, however familiar it looks: `aws_db_instance` takes `db_name`, not `name`. Not verified is for a lookup that failed, never for one you skipped.
02. **Never invent a value (IN9).** Every literal is one the user gave, one the repository already uses, or a documented constant. Sizing, retention, CIDRs, account IDs, AMIs, instance classes and engine versions you were not given become a variable with no default, or an open question in the hand-off. A plausible default is still an invention.
03. **Never widen IAM to clear an error (SE6).** Grant the one action the error names on the one resource it names, by reference (`aws_dynamodb_table.ledger.arn`). Never `*`, `service:*`, a `*` principal or an ARN with a typed account ID.
04. **Harden by default (SE7, BR2).** A new data store or exposed resource gets the baseline in step 4 even when nobody asked for it. On an existing stateful resource a hardening change can itself force replacement (`storage_encrypted` or `kms_key_id` on `aws_db_instance`), so the replacement rule (RA5) below comes first.
05. **Every address change gets a `moved` block, mapped by identity (RA3, RA7).** That covers a rename, `count` to `for_each`, and a move into or out of a module. Map each old index to the key of the object that actually sits at that index, which you learn by reading the old list, never by guessing from position.
06. **A change to an identifying argument of a stateful resource is a replacement (RA5).** `provider_schema` does not say which arguments force replacement, so assume it of anything that names or locates stored data: `identifier`, `db_name`, `engine` and `storage_encrypted` on a database, `bucket` on a bucket, `name`, `hash_key` and `range_key` on a table, `name` and `fifo_queue` on a queue. That includes a variable default or a `.tfvars` value that feeds one. Do not make the change: say it would destroy and recreate the resource and its data, and propose the additive path (a new resource beside the old one, migrate, remove the old one later) or `terraform plan -replace=ADDRESS` if the user really wants a replacement.
07. **Hold dependencies still (VE8, VE4).** Leave `.terraform.lock.hcl`, provider version constraints and module sources and versions alone unless the task is to change them. A new module call gets a version constraint, or `?ref=` on a git source.
08. **Never change real infrastructure or state.** No `apply`, `-auto-approve`, `destroy`, `import`, `taint`, `-replace` or `state` subcommand, and no `plan` against a real backend unless the user asks for one. You hand off the commands; the user runs them.
09. **A fix changes the property, not the match.** When a check or a reviewer flags something, make the underlying property true (the bucket really is private), not the flagged text disappear. After any fix, re-check the whole module, not just the flagged line.
10. **Write like the repository (ST9, LO9).** Reuse its modules, naming, tagging and file layout before you hand-roll resources. Change only what was asked: a resource the request does not mention stays as it is.

When a rule needs a decision you do not have, ask the user. When you cannot ask (a subagent or a headless run), take the safe choice (no change, a variable with no default, the narrower grant) and list it under open questions in the hand-off.

## Procedure

### 1. Read before you write

- Call `describe` on the module directory, and on the root module that calls it, for its variables, outputs, resources, module calls and required providers with file and line.
- Read `.terraform.lock.hcl` for the locked provider version, and check the backend key, workspace, account and region the root targets, so the change lands where the user means (BR11).
- Restate the request as checks the plan must pass, such as "1 to add, 0 to change, 0 to destroy" or "aws_db_instance.main moves to aws_db_instance.primary with no replacement". The hand-off reports against these.

### 2. Ground the schema

Call `provider_schema` with `path` (the module directory, relative to the project root), `type` (such as `aws_db_instance`), `kind` (`resource`, `data_source` or `provider`) and, for a nested block, `block` (such as `metadata_options`). Read the top level, then each nested block you write.

If it fails because the module has no lock entry for the provider, say so and ask for `terraform init`. If you must write anyway, list every argument you could not check under Not verified.

### 3. Source every value

Prefer, in order: an attribute of another resource (`aws_kms_key.ledger.arn`); a data source (`aws_caller_identity`, `aws_partition`, `aws_region`, `aws_ami`); an input variable; a literal the user gave. A variable you add has a type, a description, a validation where the domain is known, and no default when the value is a decision (sizing, retention, network ranges). Every caller has to supply a variable with no default (IN10): update the module calls you can see, and list the rest under Required inputs.

### 4. Harden

| Resource | Baseline |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `aws_s3_bucket` | `aws_s3_bucket_public_access_block` with all four settings true; `aws_s3_bucket_server_side_encryption_configuration`; `aws_s3_bucket_ownership_controls` with `BucketOwnerEnforced` and no `acl`; versioning; `prevent_destroy` |
| `aws_db_instance` | `storage_encrypted = true`; `manage_master_user_password = true` or `password_wo`, never a literal; `publicly_accessible = false`; `deletion_protection = true`; `skip_final_snapshot = false` with a `final_snapshot_identifier`; `prevent_destroy` |
| `aws_dynamodb_table` | `deletion_protection_enabled = true`; `point_in_time_recovery`; `server_side_encryption`; `prevent_destroy` |
| `aws_sqs_queue` | `sqs_managed_sse_enabled = true`, or `kms_master_key_id` |
| `aws_kms_key` | `enable_key_rotation = true`; `prevent_destroy` |
| `aws_security_group` | ingress through `aws_vpc_security_group_ingress_rule` from a referenced security group or a CIDR the user gave; `0.0.0.0/0` only for a public load balancer on 80 or 443 |
| IAM policies | named actions on referenced ARNs; no `*` principal; no `aws_iam_access_key` (use a role, OIDC or the service's managed secret) |
| `aws_instance` | `metadata_options { http_tokens = "required" }`; an encrypted root volume |
| `aws_lb` | `drop_invalid_header_fields = true`; `aws_lb`, never `aws_alb` |

Retention periods, lifecycle expiry and backup windows are policy, not hardening: make them a variable with no default or an open question, never a number you picked.

For a new module, copy the skeleton in assets/module-skeleton/ from `${CLAUDE_SKILL_DIR}/assets/module-skeleton/` (`versions.tf`, `variables.tf`, `main.tf`, `outputs.tf`, `README.md`, `tests/module.tftest.hcl`) and adapt it instead of writing the layout from memory. It validates and its tests pass against the AWS provider `~> 6.0`.

### 5. Change safely

- **Moves.** Write each `moved` block next to the resource it moves. Then update every reader of the old address: outputs, other resources, alarms, `depends_on`, tests and the callers `change_impact` reports (DE5). Search for the old address afterwards; a match outside a `moved` block is a missed reader.
- **`for_each` outputs.** A splat (`aws_instance.app[*].id`) does not work on a `for_each` resource. An existing output keeps its type and order, because callers depend on both: a list stays a list in the old index order, built as `[for name in local.app_names : aws_instance.app[name].id]` with `local.app_names` holding the keys in that order. Do not use `values()` or `keys()` for it, because both sort by key. Add a new output, such as the map `{ for key, instance in aws_instance.app : key => instance.id }`, only when the request asks for one.
- **Safety settings.** Never set `force_destroy = true`, `skip_final_snapshot = true`, `deletion_protection = false` or `prevent_destroy = false` to get an apply through (BR10). If the user asked to decommission something, say what will be deleted and let them make that change knowingly.
- **Providers.** Provider configuration stays in the root module. A child module that needs a second region or account declares `configuration_aliases` and takes a `providers` map (ST7).
- **Reach.** For a module other roots call, call `change_impact` with the module path (`base_ref` defaults to `HEAD`) once the edit is in, and name every root it reaches in the hand-off.

### 6. Check your own work

Run the smell grep, scripts/smell_grep.py, over every directory you touched and show its output:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/smell_grep.py DIR [DIR ...]
```

It prints `path:line: RULE message` per hit and exits 0 when clean, 1 on hits and 2 on a bad path. A hit is a cue to look, not a verdict: fix the property, or say in the hand-off why the line is deliberate. A clean run says nothing about the schema or the plan. If `python3` is not available, walk the matching sections of `references/good-vs-bad.md` by hand instead.

Then run the check-module skill on each module you changed, and map any validate failure with its table. Last, hold the diff against the standing rules: every changed address has a `moved` block, every new literal has a source, no grant got wider, no safety setting got weaker, and nothing you added (a data source, local, variable or output) sits unread or unrequested.

### 7. Hand off

End with these sections, in this order, so every run reads the same:

- **Changed**: each file and what the change in it does.
- **Expected plan**: one line per address (create, update in place, move from and to, replace), then the totals as "N to add, N to change, N to destroy". Say "0 to destroy" outright, or name what would be destroyed and why.
- **Required inputs**: new variables with no default, and who supplies each.
- **Assumptions and open questions**: every decision you made without an answer from the user.
- **Not verified**: what you could not check, such as a schema lookup that failed or a plan that was never run.
- **Next**: `terraform plan -out=tfplan`, then the explain-plan skill on that plan, then `terraform apply tfplan` after review. Never `-auto-approve`.

## References

- `references/good-vs-bad.md`: paired bad and good HCL per rubric rule, grouped as the rubric is (addressing, inputs, dependencies, blast radius, secrets and IAM, versions, structure). Read the section for the kind of change you are about to make before you write it: RA3 and RA7 for a rename or `count` to `for_each`, RA5 for a change to anything that holds data, SE6 for an IAM fix, BR2 and SE7 for a new data store.
- `${CLAUDE_PLUGIN_ROOT}/skills/review-module/references/rubric.md`: the full rubric each ID refers to. Read a rule there when the reference's example does not settle the case in front of you.

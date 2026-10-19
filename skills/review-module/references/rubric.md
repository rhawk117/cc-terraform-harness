# apply-calypse rubric

Eight categories. Every finding cites one rule ID from this file. Rule IDs the
scanner emits are marked `[scan]`; the rest are found only by reading. The
scanner's output is a map of where to look, never a finding on its own.

The single test behind every rule: **what does `terraform plan` print, and can
the reviewer predict it from the code?** Good Terraform makes the plan boring
and predictable. Bad Terraform makes it a surprise.

## Contents

1. Resource Addressing (RA)
2. Inputs and Contracts (IN)
3. Dependency Graph (DE)
4. State and Blast Radius (BR)
5. Logic and Readability (LO)
6. Secrets and Sensitivity (SE)
7. Version Discipline (VE)
8. Module and Repo Structure (ST)
9. False-positive checklist

______________________________________________________________________

## 1. Resource Addressing (RA)

Why it matters: the address is the identity Terraform uses to match code to
state. Change the address and Terraform sees a new resource and an orphan.
Every rule here is a destroy/create pair waiting to happen.

- **RA1** `[scan]` `count` used for a collection (anything other than the
  `cond ? 1 : 0` toggle). Removing or reordering an element shifts every
  later index; plan shows destroy+create for resources whose config is
  unchanged. Fix: `for_each` keyed by a stable name.
- **RA2** `[scan]` `for_each` fed by a positional collection (`range()`,
  a list literal, `csvdecode`) so keys are indices. Same failure as RA1
  in disguise.
- **RA3** `[scan, branch mode]` Address changed without a `moved` block:
  resource or module renamed, `count` converted to `for_each` or back, a
  `for_each` key scheme changed, a resource pulled into or out of a module.
  Plan will destroy the old and create the new. `moved {}` makes it a
  no-op rename.
- **RA4** `[scan]` `provisioner` blocks. They are outside the graph, cannot
  be planned, run once, and fail silently on retries. Almost always replace
  with cloud-init, user data, a config-management tool, or a separate
  apply.
- **RA5** Immutable argument changed on a stateful resource (name, zone,
  region, engine, disk type) without `create_before_destroy` or an
  explicit migration note. Plan shows `must be replaced`; reviewer should
  be able to point at the line and say so before the plan runs.
- **RA6** `for_each` keys derived from values unknown at plan time (an
  attribute of a resource created in the same apply). Fails with "invalid
  for_each argument" on first apply and forces `-target` rituals.

## 2. Inputs and Contracts (IN)

Why it matters: variables are the module's API. Untyped, undocumented, or
unvalidated inputs push failures from plan time to provider-API time, where
the error message names a field the caller never wrote.

- **IN1** `[scan]` Variable without `type`.
- **IN2** `[scan]` `type = any`. Erases the contract entirely; callers
  discover the shape by trial.
- **IN3** `[scan]` Variable without `description` (module inputs; root
  module variables that are set in one tfvars file are Low).
- **IN4** `[scan]` Output without `description`.
- **IN5** `[scan]` Environment or region literal inside a resource
  argument (`"prod"`, `"us-central1"`, `"us-east-1"`). Signals hardcoding
  that should be an input or a local. Confirm by reading: a literal in the
  single root module for that region is often fine; a literal inside a
  reusable module is not.
- **IN6** Value that clearly belongs in a `validation` block is checked
  nowhere (enumerations, CIDR shapes, name-length limits the provider
  enforces). Grade higher when the same variable feeds several resources.
- **IN8** `[scan]` `var.<name>` referenced in a directory that declares no
  such variable. `terraform validate` fails; the code was never
  initialised where the review is happening, which is itself information.
- **IN7** Copy-pasted resource blocks that differ only in a name or size,
  where a `for_each` over a typed map would express the intent.

## 3. Dependency Graph (DE)

Why it matters: Terraform's ordering comes from attribute references.
Strings that happen to equal another resource's name are invisible to the
graph; the reviewer sees a dependency, Terraform does not.

- **DE1** `[scan]` String literal that equals another resource's `name`
  (or bucket, identifier) used as an argument. Should be an attribute
  reference (`google_sql_database_instance.db.name`). Failure mode: wrong
  ordering on first apply, and a silent decoupling when the name changes.
- **DE2** `[scan]` `depends_on` present. Legitimate only for side-effect
  dependencies the graph cannot see (API enablement, IAM propagation,
  eventual consistency). Flag when the dependency is already implied by an
  attribute reference (the scanner marks these), or when `depends_on`
  appears on most resources in a file, which means references were never
  wired.
- **DE3** Hardcoded cloud resource ID (project number, VPC self-link, AMI
  ID, ARN) where a `data` source lookup or a reference would keep the
  configuration portable. Severity rises when the ID is environment-specific.
- **DE4** `depends_on` on a `module` block. Forces every resource in the
  module to wait for every resource in the target; usually a sign the
  needed output was never exposed. Medium unless justified in the module's
  README.

## 4. State and Blast Radius (BR)

Why it matters: this category is where Terraform deletes production. The
questions are: where is state, who can touch it, how much can one `apply`
reach, and what stops a plan from destroying data.

- **BR1** `[scan]` No remote backend, or a `backend "local"`, in a root
  module. State on a laptop is a single point of failure and a plaintext
  secret store with no access control. Critical when the root manages
  anything stateful.
- **BR2** `[scan]` Stateful resource (database, bucket, disk, KMS key,
  secret) without `lifecycle { prevent_destroy = true }` or the provider's
  `deletion_protection`. Confirm by reading: a child resource whose parent
  is protected (a `google_sql_database` inside a protected instance) is a
  false positive; a bucket that is intentionally ephemeral is a false
  positive only if named or documented as such.
- **BR3** `[scan]` `lifecycle { ignore_changes = all }`. Terraform stops
  managing the resource while pretending to. Anything changed out of band
  is never reconciled and never visible in plan. Narrow to the specific
  attributes or remove.
- **BR4** `[scan]` Root module declaring a large number of resources
  directly (scanner threshold 60). The signal for a monolithic state:
  long plans, lock contention, one bad refactor locking everyone out, and
  a service account for the pipeline that needs every permission.
- **BR5** `[scan, branch mode]` Address removed on the branch with no
  `removed {}` or `moved {}` block and no migration note. Plan will destroy
  it. High for anything stateful, Medium otherwise, Low if the PR text
  explains a `state rm`.
- **BR6** Environments separated only by Terraform workspaces. Workspaces
  share one backend configuration and one credential set, so dev and prod
  are isolated by a string, not by IAM. Prefer one root module per
  environment with separate state and separate identities.
- **BR7** `terraform_remote_state` reading another root's outputs where a
  `data` lookup on the real resource would work. Couples the consumer to
  the producer's output schema and requires read access to the producer's
  whole state file (which contains its secrets).
- **BR8** State split by resource type instead of by lifecycle (all IAM
  in one root, all compute in another). Changes ripple across roots, and
  cross-root references multiply.
- **BR9** No lock on the backend (backend type that supports locking with
  locking disabled, or a backend that cannot lock). Concurrent applies
  corrupt state.

## 5. Logic and Readability (LO)

Why it matters: HCL has no unit tests cheap enough to make cleverness safe.
The only test is a human reading the plan. Anything that makes the plan
harder to predict from the code is a defect, even when it is DRY.

- **LO1** `[scan]` Nested conditionals (`a ? b : c ? d : e`) inside a
  resource argument. Replace with a `locals` lookup table keyed by the
  discriminator.
- **LO2** `[scan]` Very long single expression in an argument (scanner
  threshold 200 characters). Usually a `for` expression or a `merge()`
  chain that belongs in a named local.
- **LO3** `[scan]` `dynamic` blocks nested two or more deep. Generated
  structure that nobody can read back into the plan.
- **LO4** `[scan]` Resource or module block over 80 lines. Often
  legitimate for large resources (a cluster); often a sign of inline
  policy documents that belong in `templatefile()` or a data source.
- **LO5** `[scan]` File over 400 LOC. Split by concern.
- **LO6** HCL or JSON generated by `templatefile()` or string
  concatenation and then fed back into Terraform (`jsonencode` of a
  hand-built map is fine; templating HCL is not).
- **LO7** Magic numbers and strings without a local naming them (ports,
  CIDRs, machine types repeated across resources).
- **LO8** Abstraction that hides the plan: a module with dozens of
  boolean inputs that each toggle a resource on and off, or module nesting
  three or more deep. DRY is not a virtue in Terraform when it costs plan
  predictability; three slightly repetitive root modules beat one
  40-input mega-module.
- **LO9** Naming: resource labels that repeat the type
  (`google_storage_bucket.bucket`), inconsistent case, labels that encode
  environment (`web_prod`) so the module cannot be reused.

## 6. Secrets and Sensitivity (SE)

Why it matters: state is plaintext. `sensitive = true` redacts CLI output
and nothing else. The real controls are keeping secrets out of state,
encrypting the backend, and restricting who can read it.

- **SE1** `[scan]` Secret-named argument or variable default with a string
  literal value. Critical if the value looks real; High if it is a
  placeholder that the pipeline never overrides.
- **SE2** `[scan]` Secret-named variable not marked `sensitive = true`.
- **SE3** `[scan]` Output that exposes a secret-looking value without
  `sensitive = true`. Outputs are read by anyone with state read access
  and by every `terraform_remote_state` consumer.
- **SE4** Secret generated or passed in a way that lands in state when a
  write-only argument (`password_wo`, `secret_data_wo`) or an ephemeral
  resource would keep it out. Medium; High when the provider supports
  write-only for that exact resource and the code ignores it.
- **SE5** Secret sourced from a tfvars file, `.env`, or a
  `TF_VAR_` value committed to the repository. Check `git log` for the
  history, not just the working tree; a removed secret is still in
  history.
- **SE6** Overly broad IAM as a shortcut (`roles/owner`, `roles/editor`,
  `*` in a policy action, `0.0.0.0/0` on an admin port) with no
  justification in the code or PR.

## 7. Version Discipline (VE)

Why it matters: providers are the actual API clients. An unpinned provider
means a `terraform init` on Tuesday plans differently from Monday, and a
major bump can plan replacements with no code change.

- **VE1** `[scan]` Root module without `required_version`.
- **VE2** `[scan]` Root module without `required_providers` (or a
  provider used but not listed).
- **VE3** `[scan]` Constraint shape: exact pin (`= 6.0.0`) blocks patch
  updates and rots; open-ended (`>= 6.0`) admits majors. Prefer `~>`.
  Low severity, but a pattern across all roots is Medium.
- **VE4** `[scan]` Module source without a version: git source with no
  `?ref=`, registry source with no `version`. `main` moves between plan
  and apply.
- **VE5** `[scan]` `.terraform.lock.hcl` missing or not committed. The
  lockfile pins provider hashes; without it, every machine resolves
  differently.
- **VE6** Provider major version far behind current with deprecation
  warnings in the code (deprecated arguments still in use). Low unless the
  provider has already dropped the argument.

## 8. Module and Repo Structure (ST)

Why it matters: structure decides whether the diff between dev and prod is
readable, and whether a module can be understood from its `variables.tf`.

- **ST1** `[scan]` Same-named files under sibling directories that are
  70%+ similar. The copy-pasted-environments anti-pattern. Fix: one module
  under `modules/`, thin roots under `envs/` that differ only in inputs.
- **ST2** `[scan]` Module call where nearly every input is
  `name = var.name`: a pass-through wrapper adding a layer and no
  semantics. Delete the wrapper or give it a reason to exist.
- **ST3** `[scan]` Module declaring more than 25 variables. Usually two
  modules, or one module plus a typed object variable.
- **ST4** Missing conventional layout: `main.tf`, `variables.tf`,
  `outputs.tf`, `versions.tf` (or equivalent) per module; README stating
  what the module manages and what it does not. Low individually.
- **ST5** Module with no outputs, or outputs that expose whole resource
  objects (`value = google_sql_database_instance.db`) instead of the
  attributes consumers need. Whole-object outputs leak sensitive fields
  and couple consumers to provider schema.
- **ST6** Environment-specific logic inside a reusable module
  (`if var.env == "prod"` scattered through resources). The module should
  take the sized inputs; the root decides the sizing.

______________________________________________________________________

## 9. False-positive checklist

Run every candidate finding through this before recording it.

- `count = cond ? 1 : 0` is the accepted toggle idiom, not RA1. Inside a
  module, `for_each = cond ? toset(["x"]) : toset([])` is nicer but the
  count toggle is not a finding.
- `depends_on` on `google_project_service`, IAM bindings, or
  `null_resource`/`time_sleep` for propagation is legitimate DE2 usage.
  Note it as verified-legitimate rather than as a finding.
- A region or project literal in a root module that manages exactly one
  region or project is not IN5. It is IN5 inside `modules/`.
- BR2 on a child resource whose parent has deletion protection is not a
  finding. BR2 on a `random_password` or a `null_resource` is not a
  finding (not stateful in the data sense).
- BR1 in a module under `modules/` is not a finding; only roots have
  backends. The scanner only reports BR1 for `terraform` blocks, so check
  the path.
- VE3 exact pins in a `.terraform.lock.hcl` are the point of the lockfile.
  The rule applies to `required_providers` and `required_version` only.
- LO4 on a resource that is inherently large (a GKE cluster, a
  `aws_iam_policy_document` data source) is Low at most.
- ST1 similarity between `variables.tf` files in sibling modules is
  expected when the modules share a contract. Look at `main.tf`
  similarity.
- SE1 on a literal that is obviously a placeholder AND is overridden by a
  documented pipeline variable is Medium, not Critical. Confirm the
  override exists before downgrading.
- Test fixtures and example directories (`examples/`, `test/`,
  `fixtures/`) are graded for correctness, not for BR or VE hygiene, and
  say so in the report's scope line.

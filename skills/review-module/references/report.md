# Report, grading, and verdict

The report is the deliverable. Its authority comes from three properties:
every finding cites a rule ID from `rubric.md`, every finding points at
`file:line` the reviewer actually read, and the grade and verdict follow the
arithmetic below so the reader can recompute them.

## Severity model

Severity is about what `terraform apply` would do, not about how many rules
a line violates.

- **Critical**: apply destroys or exposes data now. Address change on a
  stateful resource without `moved` (RA3/BR5 on a database, bucket with
  data, KMS key); a real secret committed in code or history (SE1/SE5);
  state on a local backend for a root that manages stateful resources
  (BR1); `ignore_changes = all` on a security control (BR3); an
  immutable argument changed on a stateful resource, including through a
  variable default (RA5); a `moved` block that points a stateful address
  at the wrong object (RA7).
- **High**: apply ships unacceptable risk or removes the net that catches
  the next mistake. `count` over a collection of stateful resources
  (RA1); unpinned providers or modules in a root (VE2/VE4/VE5); secret
  in state where write-only exists (SE4); unprotected stateful resource
  (BR2); workspaces as environment isolation (BR6); string-literal
  dependency on a stateful parent (DE1); wildcard IAM (SE6); missing
  hardening or public exposure (SE7); a weakened safety setting (BR10);
  dependency drift (VE8); the wrong execution context (BR11); a change
  that does not do what was asked (LO10); an invented value (IN9); a
  `moved` block that points a stateless address at the wrong object
  (RA7).
- **Medium**: costs real time later. Copy-pasted environments (ST1);
  nested ternaries (LO1); untyped or `any` inputs on a shared module
  (IN1/IN2); `depends_on` where a reference would do (DE2); pass-through
  wrapper modules (ST2); missing validation on an enumerated input (IN6);
  monolithic root (BR4); an argument or type not in the locked schema
  (VE7); a dangling reference (DE5); a required input with no value
  (IN10); a provider configured in a child module (ST7); CI path or apply
  assumptions (ST8); an out-of-support managed-service version (VE6).
- **Low**: polish. Missing descriptions (IN3/IN4); constraint shape (VE3);
  layout conventions (ST4); naming and tags (LO9); long files (LO5);
  hand-rolled resources beside a maintained module (ST9).

Inflation guard: Critical requires naming the plan line (`# ... must be replaced`, `# ... will be destroyed`) or the exposure path. If you cannot
write that sentence, it is High at most. Deflation guard: a missing
lockfile or an unpinned module is High even though no resource is wrong
today; reproducibility is part of the product.

## Finding format

Every finding carries:

- **ID**: BR-1, BR-2, ... stable within the report.
- **Rule**: the rubric ID (RA1, SE3, ...).
- **Severity**: per the ladder.
- **Evidence**: `file:line` plus at most one quoted line.
- **Plan impact**: the line `terraform plan` would print, or "none; plan
  is unaffected, risk is operational" when that is the honest answer.
- **Fix**: an action an engineer could take without re-deriving the
  analysis. Include the `moved {}` block, the `for_each` shape, or the
  `lifecycle` stanza when that is the fix.
- **Verify**: how to confirm the fix landed (`terraform plan` shows 0 to
  destroy; a grep returns nothing; `terraform validate` passes).
- **Confidence**: High when you read the line; Low when the finding rests
  on a scanner signal you could not fully confirm (say why).

## Category grades

Per category, from the findings in it:

- **A**: no High or Critical; at most scattered Medium/Low.
- **B**: no Critical; isolated Highs, or a consistent Medium pattern.
- **C**: a Critical exists, or Highs form a pattern (three or more
  independent instances, or one the structure forces on future code).
- **D**: Criticals plus patterned Highs; the category is systematically
  ignored.
- **F**: the category's core protection is absent (no remote state; secrets
  throughout; every collection on `count`; nothing pinned).

Plus and minus allowed near band edges.

Overall grade: weighted mean on a 4-point scale (A=4, B=3, C=2, D=1, F=0).

| Category | Weight |
| ------------------------- | ------ |
| State and Blast Radius | 2 |
| Secrets and Sensitivity | 2 |
| Resource Addressing | 2 |
| Dependency Graph | 1.5 |
| Version Discipline | 1.5 |
| Inputs and Contracts | 1.5 |
| Logic and Readability | 1 |
| Module and Repo Structure | 1 |

Bands: ≥3.7 A, ≥3.0 B, ≥2.0 C, ≥1.0 D, else F.

Hard caps, in both modes:

- No remote backend on any root that manages stateful resources: overall
  grade capped at **D**.
- A real secret in code or history: overall grade capped at **D**.
- No provider pinning and no lockfile anywhere: overall grade capped at
  **C**.

In branch mode the category grades cover only the code the branch touched
plus anything the branch's change reaches; say so in the scope line. A
branch that touches one file gets grades for the categories that file
exercises and "n/a" for the rest, and the overall grade is computed over
the graded categories only.

## Verdict

Deterministic, in both modes:

- Any Critical or High: **BLOCK**.
- Otherwise any Medium: **APPLY WITH CONDITIONS**, each condition
  enumerated with its Verify step.
- Otherwise: **CLEAR**.
- Cap: if any question about state, secrets, or address stability could
  not be answered (base branch unavailable, state backend config not in
  repo, history not readable), the verdict cannot be CLEAR. Record the gap
  in Not verified.

In repository mode the verdict answers "would I let this repository's
pipeline run `apply` against production as it stands today". In branch
mode it answers "would I let this branch's plan run".

## Flavor

Exactly one line, the epigraph under the verdict. Nothing else in the
report is funny.

- BLOCK: `Plan: <n> to add, <n> to change, <n> to destroy. Do you want to perform these actions? No.`
  Fill the numbers from the findings' plan-impact lines when you can; use
  `?` for any you cannot predict.
- APPLY WITH CONDITIONS: `Plan: 0 to destroy. Conditions apply before -auto-approve.`
- CLEAR: `Apply complete. Resources: 0 destroyed.`

## Report template

Write `APPLY-CALYPSE-REPORT.md` at the repository root unless told
otherwise. After writing, run `git check-ignore APPLY-CALYPSE-REPORT.md`;
if the file is not ignored, put the "Do not commit this file" line in and
mention it in your reply.

ALWAYS use this template:

```markdown
# APPLY-CALYPSE REPORT: <repo name | branch into base>

VERDICT: <BLOCK | APPLY WITH CONDITIONS | CLEAR>
GRADE: <letter>
> <epigraph per the flavor rules>

<Only when not git-ignored: **Do not commit this file.**>

| | |
|---|---|
| Mode | <repository | branch> |
| Scope | <n> .tf files / <LOC> LOC; <n> roots; <n> resources · <files read in full>, <n> skimmed |
| Base | <branch mode only: `<base>` @ `<merge-base sha>` ; branch `<name>` @ `<sha>`> |
| Scanner | <n> signals, <n> confirmed, <n> dismissed as false positives |

## Summary

<Three to six sentences of prose. What the code manages, where the risk
concentrates, what drives the verdict and the grade, and the single most
valuable repair. No bullets here.>

## Category grades

| Category | Grade | Determining evidence |
|---|---|---|
<all eight categories; "n/a" allowed in branch mode>

Overall: <weighted arithmetic shown, e.g. (2·4 + 2·3 + ...) / 12.5 = 3.1 → B>
<Cap applied, if any, with the rule that applied it.>

## Plan forecast

<Branch mode: the plan you predict from the diff, as `terraform plan`
would print it, one line per affected address: `# google_sql_database_instance.db will be destroyed`.
Repository mode: the addresses whose next change is most likely to
surprise, and why. If nothing would be destroyed or replaced, say
"No destroy or replace predicted.">

## Findings

<Ordered Critical, High, Medium, Low. Omit empty levels. Within a level,
State and Blast Radius first, then Secrets, then the rest.>

### <Severity>

#### <BR-n> | <rule ID> | <title>

- Evidence: `<file>:<line>` <at most one quoted line>
- Plan impact: <the plan line, or "none; risk is operational">
- Fix: <concrete action, with HCL when HCL is the fix>
- Verify: <command or check>
- Confidence: <High | Low>

## Clean categories

<One line per findings-free category: what was checked and found clean.
Absence reads as "not examined", so never omit this section.>

## Conditions

<APPLY WITH CONDITIONS only. Numbered. Each names the finding it resolves
and repeats its Verify step.>

## Not verified

<Conditional. Files skimmed, base unavailable, backend config outside the
repo, history unreadable. Each with what would resolve it.>

## Scanner signals dismissed

<One line per dismissed signal or group: rule ID, address, why the
false-positive checklist applies. Keeps the next reviewer from re-checking.>
```

Field notes:

- "Determining evidence" in the category table is one line, citing the
  finding ID that set the grade, or the fact that made it an A.
- The plan-forecast section is the persona's signature: write it even when
  the forecast is boring. A boring forecast is the point.
- Clean categories need real evidence too: "Secrets: 12 variables and 4
  outputs read; all secret-named ones marked sensitive; no literals; git
  log grep for `password =` clean" is a clean line. "Secrets: fine" is not.

Fill one copy per chunk and send it as the prompt of the terraform-author subagent. Replace every CAPITALIZED placeholder; delete a MAY line that does not apply.

```text
Chunk CHUNK_ID of MODULE-PLAN.md (mode MODE): CHUNK_TITLE.

Scope: you may change only these files: OWNED_FILES.
Root module: ROOT (the root whose plan this chunk affects; for a module-only chunk, the module directory).

Change:
CHANGE_IN_PLAIN_WORDS

Interface to honor (from MODULE-PLAN.md, do not change it):
INTERFACE_ROWS

Moved blocks to write (moves-only chunks; write them in ROOT/moved.tf, one block per row):
MOVED_ROWS

Live values every caller must still produce (names, identifiers, CIDRs):
LIVE_VALUES

Expected plan outcome: OUTCOME (create-only | no-changes | moves-only | review-required).
For moves-only: ROOT plans 0 to add, 0 to change, 0 to destroy, and each row above shows as "has moved to".

Tests: WRITE_TESTS (write .tftest.hcl with command = plan and mock_provider; do not run terraform test against real credentials).
Init: terraform init -backend=false MAY_OR_MAY_NOT run for validate.
Do not commit. Do not run plan against a backend, apply, import or any state command.
If the change cannot be made inside the scope, or would replace a resource, stop and report blocked with the reason.
```

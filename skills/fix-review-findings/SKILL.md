---
name: fix-review-findings
disable-model-invocation: true
allowed-tools: mcp__plugin_terraform-harness_terraform__diagnostics mcp__plugin_terraform-harness_terraform__plan_digest
description: >-
  Work through a review-module report (APPLY-CALYPSE-REPORT.md) one finding at a time: the user picks the
  findings and whether to commit, then terraform-author fixes each finding in report order, the module is
  checked after every fix, and a hand-off table closes the run. Slash command only; invoke it with the path
  to the report.
---

# Fix review findings

Turn a review-module report into a series of small, separately verified changes. You dispatch and route; `terraform-author` writes. You never edit the report, and you never write Terraform yourself.

The argument is the path to the report. A finding in it carries an ID, a rule, a severity, Evidence, Plan impact, Fix and Verify (the format in `skills/review-module/references/report.md`). If the path is missing or holds no findings, say so and stop.

## Choose what to fix

Read the report once. Then ask one `AskUserQuestion` dialog with two questions:

1. Which findings to fix. List each finding as ID, severity and rule. Offer, recommended first: the Critical and High findings, all findings, or pick by ID.
2. Whether to commit per finding or leave the changes uncommitted.

Ask these two questions once, together; do not repeat them per finding.

When `AskUserQuestion` is not available, ask the same two questions in one plain-text message. Number the two questions, write each as a question ending in a question mark, and letter its choices with the recommended choice first, marked recommended. List each finding as ID, severity and rule, as in the dialog. Keep all three choices for question 1, even when two of them select the same findings. Stop until the user answers.

## Run the loop

Take the chosen findings in report order. For each one, run the steps below to the end before starting the next.

1. **Dispatch `terraform-author` once**, with these inputs:
   - Scope: the file in the finding's Evidence, and the root module it belongs to.
   - Change: the finding's Fix, quoted, with its rule ID and its Verify line.
   - Expected plan outcome, derived from Plan impact: `create-only`, `no-changes`, `moves-only`, or `review-required` with the actions named. When Plan impact does not settle it ("none; risk is operational" does not), use `review-required` and name the actions the Fix implies; if you cannot name them, ask the user.
   - When commits are on: the instruction to commit this finding alone, with a message that names the rule and the scope.
2. **Read the author's report.** `<status>done</status>` with no failing `<gate>` goes to step 3. Anything else goes to Escalate.
3. **Run the `check-module` skill** on the touched module and compare its result with the finding's Verify line. A failing check is a failed gate for Escalate, and its output is what you hand back. Then run the finding's Verify line yourself when it is a read-only command the session may run (a grep, `terraform validate`). When it needs a plan or anything not permitted, do not run it: the outcome is "fixed, unverified", and you name the unrun Verify line under the hand-off table.
4. **Record the outcome** (fixed, "fixed, unverified", deferred as unresolved, or not reached), the commit SHA when there is one, and any `<question>` the author left, for the hand-off.

## Escalate

Route a `blocked` or failed author report by its kind:

- **A `<question>`**: ask the user. Re-dispatch the author once with the answer.
- **A fact gap** (consumers, addresses, roots the author could not establish): dispatch `terraform-researcher` with that one question and the path it concerns. Re-dispatch the author once with the facts it returns.
- **A `<gate result="fail">`**: re-dispatch the author once with the failing output.
- **A conflict with the expected plan, or a second failure on the same finding**: dispatch `terraform-advisor` with the question, the finding and the reports so far. Then ask the user, with exactly these choices:
  1. Re-dispatch with the user's answer.
  2. Take the advisor's alternative.
  3. Defer the finding to the hand-off as unresolved.
  4. Stop the loop.
- **Any other blocked report** (for example a scope boundary or an unavailable describe named in `<blocking>`): go straight to the user, quote the author's `<blocking>` text, and offer the same four choices as the conflict route. Add no fifth choice.

No finding is set aside without the user choosing it. Stopping the loop still ends with the hand-off table.

## Hand off

End with one table, one row per chosen finding:

| Finding | Rule | Severity | Outcome | Commit |
| --- | --- | --- | --- | --- |

Outcome is fixed, "fixed, unverified", deferred as unresolved, or not reached. Commit is the SHA, or `-` when none. Under the table list each open `<question>`, each deferred finding's reason, each "fixed, unverified" finding's unrun Verify line, and any follow-up the author named for the user to run. The report is unchanged.

---
name: trace-change-impact
allowed-tools: mcp__plugin_terraform-harness_terraform__change_impact
description: >-
  Trace what a Terraform change touches: which blocks changed, how module
  variables and outputs changed, and which root modules reach a changed
  module. Use before editing or merging a module that other roots call, when
  the user asks "what does this change affect", "who uses this module", or
  "is this change breaking".
---

# Trace change impact

Find the blast radius of a change before it reaches a plan.

Call `change_impact` with:

- `path`: a directory inside the project, relative to the project root. Changes are the working tree, staged and untracked `.tf` files under it.
- `base_ref`: the git ref to compare against, `HEAD` by default. The comparison runs against the merge base of the ref and `HEAD`, so pass the default branch to review a whole feature branch.

The result lists the changed blocks (added, modified or removed, a removed block located at its base file and line), each changed module's variable and output changes (added, removed, type or default changed), and every root module in the whole project that reaches a changed module, with its shortest module call path. It reads only git and the files; there is no plan or state.

Read the result as a contract check. A removed or retyped variable or output breaks every root in the list that sets or reads it. A new variable without a default breaks every caller. Name the affected roots and the call path, then say which ones need a plan before the change merges. Do not claim what a plan would print; that needs `plan_digest` on a rendered plan.

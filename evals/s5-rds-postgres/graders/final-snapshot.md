---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: 'skip_final_snapshot\s*=\s*true'
match: not_contains
---

A destroy still takes a final snapshot.

---
type: regex
target: {source: file, path: modules/billing/variables.tf}
pattern: '"db\.[a-z0-9]+\.[a-z0-9]+"'
match: not_contains
---

No instance class was invented as a variable default.

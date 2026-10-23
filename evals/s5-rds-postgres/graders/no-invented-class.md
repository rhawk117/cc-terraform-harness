---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: '"db\.[a-z0-9]+\.[a-z0-9]+"'
match: not_contains
---

No instance class was invented in the resource or a variable default beside it.

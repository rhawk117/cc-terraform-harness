---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: 'publicly_accessible\s*=\s*true'
match: not_contains
---

The database is not reachable from the internet.

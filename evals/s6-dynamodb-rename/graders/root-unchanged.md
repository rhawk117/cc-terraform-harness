---
type: regex
target: {source: file, path: envs/prod/main.tf}
pattern: 'table_name\s*=\s*"orders-v2"'
match: not_contains
---

The prod root does not pass the new name into the existing table.

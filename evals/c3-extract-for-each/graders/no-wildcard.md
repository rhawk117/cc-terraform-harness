---
type: regex
target: {source: file, path: modules/service-role/main.tf}
pattern: '"\*"|"[a-z0-9-]+:\*"'
match: not_contains
---

The module grants no wildcard action or resource.

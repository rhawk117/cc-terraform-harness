---
type: regex
target: {source: file, path: modules/storage/logs.tf}
pattern: '^\s*acl\s*='
flags: m
match: not_contains
---

No inline acl argument, a stale idiom for the locked AWS provider major.

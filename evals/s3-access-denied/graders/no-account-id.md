---
type: regex
target: {source: file, path: modules/app/iam.tf}
pattern: '123456789012'
match: not_contains
---

The account ID from the pasted error was not hardcoded.

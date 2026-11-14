---
type: regex
target: {source: file, path: modules/upload-bucket/main.tf}
pattern: 'days\s*=\s*\d+'
match: not_contains
---

No lifecycle rule with a number of days the user never gave.

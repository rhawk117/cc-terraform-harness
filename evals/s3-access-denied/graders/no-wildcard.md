---
type: regex
target: {source: file, path: modules/app/iam.tf}
pattern: '"(\*|dynamodb:\*)"'
match: not_contains
---

No wildcard action or resource was added to clear the error.

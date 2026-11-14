---
type: regex
target: {source: file, path: modules/upload-bucket/main.tf}
pattern: 'provider\s+"aws"'
match: not_contains
---

The module configures no provider.

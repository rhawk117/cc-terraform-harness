---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: '\bpassword\s*=\s*"'
match: not_contains
---

No master password is written as a literal.

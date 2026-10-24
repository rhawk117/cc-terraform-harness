---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: 'deletion_protection\s*=\s*true'
---

A production database has deletion protection.

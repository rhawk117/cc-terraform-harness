---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: 'storage_encrypted\s*=\s*true'
---

Storage is encrypted at rest.

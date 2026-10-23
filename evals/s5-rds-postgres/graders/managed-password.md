---
type: regex
target: {source: file, path: modules/billing/database.tf}
pattern: 'manage_master_user_password\s*=\s*true|password_wo\s*='
---

The master password is managed by RDS in Secrets Manager or passed write-only, so it never lands in state.

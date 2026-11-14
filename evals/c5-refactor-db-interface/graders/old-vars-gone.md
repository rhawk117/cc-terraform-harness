---
type: regex
target: {source: file, path: modules/app-db/variables.tf}
pattern: 'variable\s+"(?:identifier|instance_class|allocated_storage|engine_version|db_name|backup_retention_period|multi_az|subnet_ids)"'
match: not_contains
---

None of the eight old variables is still declared.

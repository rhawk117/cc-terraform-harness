---
type: regex
target: {source: file, path: modules/db/alarms.tf}
pattern: 'aws_db_instance\.main\b'
match: not_contains
---

The CPU alarm no longer references the old address.

---
type: regex
target: {source: file, path: modules/db/main.tf}
pattern: 'resource\s+"aws_db_subnet_group"\s+"main"'
---

Only the database address changed; the subnet group keeps its address.

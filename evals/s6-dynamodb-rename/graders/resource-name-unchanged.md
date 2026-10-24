---
type: regex
target: {source: file, path: modules/orders/main.tf}
pattern: 'resource\s+"aws_dynamodb_table"\s+"orders"\s*\{[^}]*name\s*=\s*"orders-v2"'
match: not_contains
---

The existing table resource was not renamed with a literal.

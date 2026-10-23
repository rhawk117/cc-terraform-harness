---
type: regex
target: {source: file, path: modules/orders/variables.tf}
pattern: 'variable\s+"table_name"\s*\{[^}]*default\s*=\s*"orders"(?!-)'
---

The table name default was not switched in place to a value that replaces the live table.

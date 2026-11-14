---
type: regex
target: {source: file, path: modules/network/main.tf}
pattern: 'provider\s+"aws"|backend\s+"'
match: not_contains
---

The module main.tf configures no provider and no backend; the calling root owns both.

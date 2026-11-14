---
type: regex
target: {source: file, path: modules/data/main.tf}
pattern: 'prevent_destroy\s*=\s*true[\s\S]*prevent_destroy\s*=\s*true'
---

The module keeps prevent_destroy on both data stores.

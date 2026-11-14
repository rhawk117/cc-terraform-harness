---
type: regex
target: {source: file, path: modules/data/main.tf}
pattern: '(?:identifier|name)\s*=\s*"[^"\n]*\$\{'
match: not_contains
---

No identifier or name is rebuilt by interpolating a prefix, which would rename and replace a live store.

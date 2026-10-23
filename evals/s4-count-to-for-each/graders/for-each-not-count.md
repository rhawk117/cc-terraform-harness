---
type: regex
target: {source: file, path: modules/workers/main.tf}
pattern: '^(?![\s\S]*\bcount\s*=)[\s\S]*for_each\s*='
---

The worker resource uses for_each and no count argument remains.

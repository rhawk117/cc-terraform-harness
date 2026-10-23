---
type: regex
target: {source: file, path: modules/workers/outputs.tf}
pattern: 'aws_instance\.worker\[\*\]'
match: not_contains
---

The output no longer uses a list splat, which does not work on a for_each map.

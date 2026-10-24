---
type: regex
target: {source: file, path: modules/storage/logs.tf}
pattern: 'prevent_destroy\s*=\s*true'
---

The bucket holds data, so it carries lifecycle prevent_destroy.

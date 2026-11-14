---
type: regex
target: {source: file, path: modules/app-db/variables.tf}
pattern: 'variable\s+"database"[\s\S]*?object\(\{[\s\S]*optional\('
---

variable "database" is a typed object that uses optional() for its optional attributes.

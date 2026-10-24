---
type: regex
target: trace
pattern: '^(?:(?!\\*"name\\*"\s*:\s*\\*"(?:Write|Edit)\\*")[\s\S])*?\\*"name\\*"\s*:\s*\\*"Read\\*"[^\n]*?(?:\.pre-commit-config\.yaml|\.tflint\.hcl|Makefile)'
---

The run read one of the repository's tooling files (.pre-commit-config.yaml, .tflint.hcl or Makefile) before any Write or Edit call.

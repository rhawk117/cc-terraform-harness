---
type: regex
target: trace
pattern: '^(?:(?!\\*"name\\*"\s*:\s*\\*"(?:Write|Edit)\\*")[\s\S])*?\\*"name\\*"\s*:\s*\\*"Read\\*"\s*,\s*\\*"input\\*"\s*:\s*\{\s*\\*"file_path\\*"\s*:\s*\\*"(?:[^"\\]*/)?(?:\.pre-commit-config\.yaml|\.tflint\.hcl|Makefile)\\*"'
---

The run read one of the repository's tooling files (.pre-commit-config.yaml, .tflint.hcl or Makefile) before any Write or Edit call.

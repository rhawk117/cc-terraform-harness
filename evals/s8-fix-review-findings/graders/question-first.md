---
type: regex
target: trace
pattern: '^(?:(?!\\*"name\\*"\s*:\s*\\*"(?:Agent|Write|Edit)\\*")[\s\S])*?\\*"name\\*"\s*:\s*\\*"AskUserQuestion\\*"[^\n]*?BR-\d'
---

An AskUserQuestion call naming the findings (BR-n) came before any Agent, Write or Edit call.

---
type: regex
target: trace
pattern: '^(?:(?!\\*"name\\*"\s*:\s*\\*"(?:Agent|Write|Edit)\\*")[\s\S])*?"type"\s*:\s*"text"\s*,\s*"text"\s*:\s*"(?:[^"\\]|\\.)*?BR-\d(?:[^"\\]|\\.)*?[Cc]ommit(?:[^"\\?]|\\.)*\?'
---

An assistant text block naming a finding (BR-n) and asking about committing came before any Agent, Write or Edit call.

---
type: regex
target: trace
pattern: 'moved\s*\{(?:\\n|\s)*from\s*=\s*aws_db_instance\.main(?:\\n|\s)*to\s*=\s*aws_db_instance\.primary'
---

A moved block maps aws_db_instance.main to aws_db_instance.primary, so the plan shows a move instead of a destroy and a create.

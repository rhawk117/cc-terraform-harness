---
type: regex
target: trace
pattern: 'moved\s*\{(?:\\n|\s)*from\s*=\s*aws_db_instance\.orders(?:\\n|\s)*to\s*=\s*module\.[\w-]+\.aws_db_instance\.\w+'
---

A moved block maps aws_db_instance.orders into the module call.

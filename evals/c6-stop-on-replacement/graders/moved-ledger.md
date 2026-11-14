---
type: regex
target: trace
pattern: 'moved\s*\{(?:\\n|\s)*from\s*=\s*aws_dynamodb_table\.ledger(?:\\n|\s)*to\s*=\s*module\.[\w-]+\.aws_dynamodb_table\.\w+'
---

A moved block maps aws_dynamodb_table.ledger into the module call.

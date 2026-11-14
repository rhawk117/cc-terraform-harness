---
type: regex
target: trace
pattern: '(?:moved\s*\{(?:\\n|\s)*from\s*=\s*aws_sqs_queue\.orders(?:\\n|\s)*to\s*=\s*module\.[\s\S]*){2}'
---

A moved block from aws_sqs_queue.orders into the module call is written at least twice, once per root.

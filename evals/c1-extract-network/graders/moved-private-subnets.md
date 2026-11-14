---
type: regex
target: trace
pattern: 'moved\s*\{(?:\\n|\s)*from\s*=\s*aws_subnet\.private(?:\[\d\])?(?:\\n|\s)*to\s*=\s*module\.network\.aws_subnet\.\w+'
---

A moved block maps the counted private subnets into module.network.

---
type: regex
target: trace
pattern: 'moved\s*\{(?:\\n|\s)*from\s*=\s*aws_vpc\.main(?:\\n|\s)*to\s*=\s*module\.network\.aws_vpc\.\w+'
---

A moved block maps aws_vpc.main into module.network, so the VPC moves in state instead of being destroyed.

---
type: llm
focus: {source: file, path: modules/network/variables.tf}
---

PASS if the module variables for the VPC CIDR, the subnet CIDRs and the availability zones are declared with a type and no default value.
FAIL if any of them has a default (for example a 10.x.0.0/16 literal or a list of zones), or if CIDRs are hardcoded instead of being variables.

---
type: llm
focus: {source: file, path: modules/orders-queue/variables.tf}
---

PASS if the variables for message retention and the alarm threshold are declared with a type and no default value.
FAIL if either has a default, or if either value is hardcoded in the module instead of being a variable.

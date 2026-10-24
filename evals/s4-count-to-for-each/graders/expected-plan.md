---
type: llm
focus: last_message
---

PASS if the final message tells the user what terraform plan should show: three instances moved in state from index keys to the named keys (ingest, transform, publish), with no instance destroyed, created, or replaced.
FAIL if the message does not state the expected plan outcome, says instances will be replaced or recreated, or tells the user to run terraform apply -auto-approve.

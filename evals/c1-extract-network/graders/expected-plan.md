---
type: llm
focus: last_message
---

PASS if the final message tells the user the expected terraform plan for envs/prod: the network resources move into module.network with nothing destroyed, created or replaced (for example "0 to destroy" or "moves only").
FAIL if it does not state the expected plan, predicts any network resource is replaced or recreated, or tells the user to run terraform apply -auto-approve.

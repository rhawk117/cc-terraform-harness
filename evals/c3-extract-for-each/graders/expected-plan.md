---
type: llm
focus: last_message
---

PASS if the final message gives the expected terraform plan for envs/prod: the three roles and their policies move into module instances keyed api, worker and billing, with nothing destroyed, created or replaced.
FAIL if it does not state the expected plan, predicts a role is replaced or recreated, or tells the user to run terraform apply -auto-approve.

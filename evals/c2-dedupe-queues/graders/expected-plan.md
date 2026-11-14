---
type: llm
focus: last_message
---

PASS if the final message gives an expected terraform plan for each of envs/dev and envs/prod: the queue, dead-letter queue and alarm move into the module with nothing destroyed, created or replaced in either root.
FAIL if it covers only one root, predicts a queue is replaced or recreated, or tells the user to run terraform apply -auto-approve.

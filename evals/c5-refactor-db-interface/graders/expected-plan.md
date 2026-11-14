---
type: llm
focus: last_message
---

PASS if the final message says terraform plan should show no changes in both envs/staging and envs/prod (the refactor only changes how values reach the module).
FAIL if it omits either root, predicts any database change or replacement, or tells the user to run terraform apply -auto-approve.

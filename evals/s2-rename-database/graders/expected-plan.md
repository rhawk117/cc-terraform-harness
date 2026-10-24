---
type: llm
focus: last_message
---

PASS if the final message tells the user what terraform plan should show for this change: the database moves or is renamed in state from aws_db_instance.main to aws_db_instance.primary, with nothing destroyed, created, or replaced (for example "0 to destroy" or "no replacement").
FAIL if the message does not state the expected plan outcome, says the database will be replaced or recreated, or tells the user to run terraform apply -auto-approve.

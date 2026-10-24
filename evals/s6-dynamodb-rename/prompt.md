---
description: Rename a live DynamoDB table whose name forces replacement.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Rename the orders DynamoDB table to orders-v2.

Everything you'd otherwise ask me: the Terraform is in modules/orders, and envs/prod is the root that calls the module. I can't answer anything else right now. Don't run terraform plan or apply.

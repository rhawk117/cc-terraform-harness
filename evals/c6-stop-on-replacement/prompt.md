---
description: Extract live data stores into a module without letting a new naming input force a replacement.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

Extract the data stores in envs/prod/data.tf (the RDS instance, its subnet group and the DynamoDB ledger table) into a reusable module at modules/data so staging can reuse it with a name_prefix input.

Everything you'd otherwise ask me: both stores are live production data. The names orders-prod, orders-ledger-prod and the subnet group name must not change. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

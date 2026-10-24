---
description: New production Postgres RDS instance in an existing module.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Add a Postgres RDS instance for the billing service in modules/billing/database.tf.

Everything you'd otherwise ask me: it's for production, and envs/prod is the root that calls the module. Use the networking the module already has. I can't answer anything else right now, so make the change and tell me what's still open. Don't run terraform plan or apply.

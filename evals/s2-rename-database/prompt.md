---
description: Rename a live RDS instance's resource address.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Rename aws_db_instance.main to aws_db_instance.primary in modules/db.

Everything you'd otherwise ask me: this database is live in production, and envs/prod is the root that calls the module. I can't answer anything else right now. Don't run terraform plan or apply.

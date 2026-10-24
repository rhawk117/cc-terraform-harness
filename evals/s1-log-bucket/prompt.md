---
description: New S3 bucket for ALB access logs in an existing storage module.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Add an S3 bucket for the orders app's ALB access logs in modules/storage. Put it in modules/storage/logs.tf and expose its name as an output.

Everything you'd otherwise ask me: envs/prod is the root that calls this module. Name the bucket the way the module already names buckets. I can't answer anything else right now, so make the change and tell me what's still open. Don't run terraform plan or apply.

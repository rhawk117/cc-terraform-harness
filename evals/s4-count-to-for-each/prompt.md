---
description: Convert a counted resource to for_each without replacing instances.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Convert aws_instance.worker in modules/workers from count = 3 to for_each over named workers. Index 0 is ingest, 1 is transform, 2 is publish.

Everything you'd otherwise ask me: these instances are running in production, and envs/prod is the root that calls the module. I can't answer anything else right now. Don't run terraform plan or apply.

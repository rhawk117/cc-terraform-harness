---
description: Collapse a module's eight database variables into one typed object without changing either caller's plan.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

Change modules/app-db to take one `database` object variable instead of the eight separate ones.

Everything you'd otherwise ask me: envs/staging and envs/prod both call the module and both databases are live. The refactor must not change either database. Update both callers. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

---
description: Extract a for_each set of IAM roles into a module called once per service.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

Extract the per-service IAM role and inline policy in envs/prod/iam.tf into a module at modules/service-role, called once per service.

Everything you'd otherwise ask me: these roles are live in production and the running ECS tasks assume them, so they must not be recreated. envs/prod is the only root. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

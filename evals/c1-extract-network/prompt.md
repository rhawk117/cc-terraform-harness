---
description: Extract a live production network from a root module into a reusable module.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

Pull the VPC, subnets, internet gateway, NAT gateway and route tables out of envs/prod into a reusable network module at modules/network, and have envs/prod call it.

Everything you'd otherwise ask me: this network is live in production and envs/prod is the only root today, though staging will call the module next quarter with its own CIDRs. The security group in envs/prod/app.tf stays in the root. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

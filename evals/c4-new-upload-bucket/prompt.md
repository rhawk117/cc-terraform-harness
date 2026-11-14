---
description: Design and write a new reusable, hardened S3 upload bucket module.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

Write a reusable module at modules/upload-bucket for an encrypted S3 bucket our services can use for uploads.

Everything you'd otherwise ask me: envs/staging and envs/prod will call it later; don't add the calls yet. Each root already has a KMS key (aws_kms_key.app) the bucket should be encrypted with. I have not decided how long uploads are kept. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

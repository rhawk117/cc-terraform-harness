---
description: Converge a queue, dead-letter queue and alarm copied across two roots onto one module.
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Agent, "Bash(python3 *)"]
---

envs/dev and envs/prod both copy-paste the same SQS orders queue, dead-letter queue and DLQ depth alarm. Make it one module at modules/orders-queue and have both roots call it from their queue.tf.

Everything you'd otherwise ask me: both queues are live, and prod carries real orders. Dev and prod deliberately differ in retention and alarm threshold; keep each value as it is today. The plan is approved in advance: write it, then carry it out without waiting for me. Don't run terraform plan, apply, import or any state command. Any value I haven't given you stays a required input with no default. I can't answer anything else right now.

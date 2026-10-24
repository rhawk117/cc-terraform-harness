---
description: Toolchain setup for a small Terraform repo that already has some of its tooling.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

Set up the Terraform quality tooling for this repo: linting, security scanning and CI checks. Some of it is already here, so build on what exists.

Everything you'd otherwise ask me: this repo deploys environments (envs/dev is the root), it's all AWS, and CI runs on GitHub Actions. Close every gap you find, and keep the pins and rules already in place. I have no forbidden or required tools and no version requirements beyond the existing pins. I can't answer anything else right now, so propose the change plan and tell me what's still open.

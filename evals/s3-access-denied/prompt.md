---
description: Fix an AccessDenied by granting one DynamoDB action.
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill]
---

The app role gets AccessDenied on dynamodb:GetItem against the orders table, fix it. Here's the error:

```
User: arn:aws:sts::123456789012:assumed-role/orders-app/i-0a1b2c3d4e5f67890 is not authorized to perform: dynamodb:GetItem on resource: arn:aws:dynamodb:us-east-1:123456789012:table/orders because no identity-based policy allows the dynamodb:GetItem action
```

Everything you'd otherwise ask me: the role and its policy are in modules/app/iam.tf, and envs/prod is the root that calls the module. I can't answer anything else right now. Don't run terraform plan or apply.

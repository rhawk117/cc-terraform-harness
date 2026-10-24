---
type: regex
target: {source: file, path: modules/app/iam.tf}
pattern: 'aws_dynamodb_table\.orders\.arn'
---

The grant is scoped to the orders table through a reference, not a pasted ARN.

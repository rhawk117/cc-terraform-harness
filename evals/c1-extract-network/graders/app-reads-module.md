---
type: regex
target: {source: file, path: envs/prod/app.tf}
pattern: '^(?![\s\S]*aws_vpc\.main\.)[\s\S]*module\.network\.'
---

The security group in envs/prod/app.tf reads the VPC through a module.network output, not the old address.

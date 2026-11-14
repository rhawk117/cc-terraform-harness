---
mode: extract
module: modules/NAME
sources: [envs/prod]
callers: [envs/prod]
terraform: ">= 1.7"
status: draft
approved_by: user
---

# Module plan: modules/NAME

## Inventory

Base ref: HEAD at COMMIT.

| root | address | count / for_each | readers |
| --- | --- | --- | --- |
| envs/prod | aws_vpc.main | none | aws_security_group.app (app.tf:3), output vpc_id (outputs.tf:1) |

## Interface

| kind | name | type | required | why |
| --- | --- | --- | --- | --- |
| variable | vpc_cidr | string | yes | differs per caller; a network decision, so no default |
| output | vpc_id | string | n/a | read by aws_security_group.app and output vpc_id |

## Moved map

| root | from | to |
| --- | --- | --- |
| envs/prod | aws_vpc.main | module.network.aws_vpc.main |

## Chunks

| id | title | owned | outcome | status |
| --- | --- | --- | --- | --- |
| C1 | module: versions, variables, resources, outputs | modules/NAME/versions.tf, modules/NAME/variables.tf, modules/NAME/main.tf, modules/NAME/outputs.tf | no-changes | pending |
| C2 | envs/prod: module call, moved.tf, readers re-pointed | envs/prod/main.tf, envs/prod/moved.tf, envs/prod/app.tf | moves-only | pending |
| C3 | tests, README, examples/basic | modules/NAME/tests/module.tftest.hcl, modules/NAME/README.md, modules/NAME/examples/basic/main.tf | no-changes | pending |

## Expected plan

- envs/prod: 0 to add, 0 to change, 0 to destroy (1 move: aws_vpc.main has moved to module.network.aws_vpc.main)

## Open questions

- None.

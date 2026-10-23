# Good and bad Terraform, by rubric rule

Paired HCL for the mistakes that look fine on the page. Each pair cites the review-module rubric ID a reviewer would file it under. Read the sections for the resource types and changes in front of you before writing. Every block labelled `Good:` validates against the AWS provider 6.69.1 (`~> 6.0`); blocks labelled `Fix:` are fragments of a larger block.

Contents:

1. Resource addressing: RA1, RA3, RA5, RA7
2. Inputs: IN9, IN10
3. Dependency graph: DE1, DE3, DE5
4. State and blast radius: BR2, BR10, BR11
5. Secrets and IAM: SE1, SE4, SE6, SE7
6. Versions: VE4, VE6, VE7, VE8
7. Structure: ST7, ST9, LO9

## 1. Resource addressing

### RA1: `count` over a collection

Removing the first name shifts every later index, and the plan replaces queues whose configuration never changed.

Bad:

```hcl
resource "aws_sqs_queue" "jobs" {
  count = length(var.job_names)
  name  = "${var.name_prefix}-${var.job_names[count.index]}"
}
```

Good:

```hcl
resource "aws_sqs_queue" "jobs" {
  for_each = toset(var.job_names)

  name                    = "${var.name_prefix}-${each.key}"
  sqs_managed_sse_enabled = true
}
```

### RA3: an address change without a `moved` block

Renaming a label reads to Terraform as destroy the old address and create a new one. For a KMS key that means every ciphertext under the old key becomes unreadable once the key is deleted.

Bad:

```hcl
resource "aws_kms_key" "ledger" {
  description = "Ledger data key"
}
```

The block above was `aws_kms_key.this` before the edit, and nothing records the move.

Good:

```hcl
resource "aws_kms_key" "ledger" {
  description         = "Ledger data key"
  enable_key_rotation = true

  lifecycle {
    prevent_destroy = true
  }
}

moved {
  from = aws_kms_key.this
  to   = aws_kms_key.ledger
}
```

The same holds for `count` to `for_each`: one `moved` block per existing index, mapped to the key that index really is. Here the user said index 0 is `api`, 1 is `batch` and 2 is `admin`.

Good:

```hcl
resource "aws_instance" "app" {
  for_each = toset(["api", "batch", "admin"])

  ami           = data.aws_ami.al2023.id
  instance_type = var.instance_type
  subnet_id     = var.subnet_id

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    encrypted = true
  }

  tags = {
    Name = "${var.name_prefix}-${each.key}"
  }
}

moved {
  from = aws_instance.app[0]
  to   = aws_instance.app["api"]
}

moved {
  from = aws_instance.app[1]
  to   = aws_instance.app["batch"]
}

moved {
  from = aws_instance.app[2]
  to   = aws_instance.app["admin"]
}
```

Outputs that used the splat `aws_instance.app[*].id` stop working on a map. Rewrite them as `{ for name, instance in aws_instance.app : name => instance.id }` in the same change.

### RA7: a `moved` block that points at the wrong object

Valid HCL, and the plan shows no replacement, yet state now ties `aws_instance.app["api"]` to the machine that runs batch jobs. Nothing fails until someone changes `api` and the wrong instance moves. Take the mapping from the user or from what each instance is (its `Name` tag or ID in `terraform state show`), never from position or label similarity. When you cannot see state and the user has not said, ask, and say in the hand-off which mapping you assumed.

### RA5: a replace-forcing change to something that holds data

A DynamoDB table's `name` cannot change in place. Bumping it, here through a variable default, destroys the table and creates an empty one. A `moved` block does not help, because the address is unchanged.

Bad:

```hcl
variable "table_name" {
  type    = string
  default = "ledger-v2"
}

resource "aws_dynamodb_table" "ledger" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}
```

Good: leave the live table alone, add the new one beside it, and tell the user the rest of the path: copy or stream the data across, move readers and writers, then retire the old table in a later change.

```hcl
resource "aws_dynamodb_table" "ledger" {
  name                        = "ledger"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "id"
  deletion_protection_enabled = true

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.ledger.arn
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_dynamodb_table" "ledger_v2" {
  name                        = "ledger-v2"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "id"
  deletion_protection_enabled = true

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.ledger.arn
  }

  lifecycle {
    prevent_destroy = true
  }
}
```

When the user only wants the name to change and accepts losing the data, that is their call to make after you have said so. Make no edit that causes the replacement before they confirm. A deliberate single replacement is `terraform apply -replace=ADDRESS` on a saved plan, not a destroy and a re-apply.

## 2. Inputs

### IN9: invented values

A size, CIDR, retention period, engine version or region that nobody asked for reads exactly like a deliberate choice, and nobody revisits it.

Bad:

```hcl
resource "aws_cloudwatch_log_group" "app" {
  name              = "/app/ledger"
  retention_in_days = 90
}

variable "instance_class" {
  type    = string
  default = "db.t3.medium"
}
```

Good: no default, a validation that catches typos, and a line in the hand-off under Required inputs.

```hcl
variable "instance_class" {
  type        = string
  description = "RDS instance class for the ledger database. No default: sizing is the caller's decision."

  validation {
    condition     = startswith(var.instance_class, "db.")
    error_message = "instance_class must be an RDS instance class."
  }
}

variable "log_retention_days" {
  type        = number
  description = "Days to keep ledger logs. No default: retention is a policy decision."

  validation {
    condition     = var.log_retention_days > 0
    error_message = "log_retention_days must be a positive number of days."
  }
}
```

A value the repository already uses for the same purpose (the sibling bucket's naming pattern, the subnet group every database in the module shares) is sourced. Cite it in the hand-off.

### IN10: a required input nobody supplies

Adding a variable with no default to a module breaks every caller until each one passes it. Update the module calls in scope, and list the ones outside your scope in the hand-off with the variable they now need.

Fix:

```hcl
module "ledger" {
  source = "../../modules/ledger"

  instance_class     = var.ledger_instance_class
  log_retention_days = var.ledger_log_retention_days
}
```

## 3. Dependency graph

### DE1 and DE3: literals where a reference or a data source belongs

A pasted ARN, account ID or AMI ID breaks in the next account or region, and a name typed as a string is invisible to the graph.

Bad:

```hcl
resource "aws_iam_role_policy" "app_ssm" {
  role = "ledger-app"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:aws:ssm:us-east-1:111122223333:parameter/ledger/*"
    }]
  })
}

resource "aws_instance" "bastion" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}
```

Good:

```hcl
data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_iam_role_policy" "app_ssm" {
  role = aws_iam_role.app.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameter"]
      Resource = "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/*"
    }]
  })
}
```

### DE5: a rename that misses a reader

Renaming `aws_db_instance.ledger` in `main.tf` and leaving `outputs.tf` and `alarms.tf` on the old address fails `validate` with `Reference to undeclared resource`. Before renaming or removing an address, search the module for every reference to it, and run `change_impact` when module outputs or variables change, because other roots may read them.

## 4. State and blast radius

### BR2: a data store with nothing stopping a destroy

Bad:

```hcl
resource "aws_db_instance" "ledger" {
  engine              = "postgres"
  instance_class      = var.instance_class
  allocated_storage   = 20
  skip_final_snapshot = true
}
```

Good: the full database baseline, every size and version from an input, the password managed by RDS in Secrets Manager.

```hcl
resource "aws_db_instance" "ledger" {
  identifier     = "${var.name_prefix}-ledger"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class
  db_name        = "ledger"
  username       = "ledger_admin"

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true
  kms_key_id        = aws_kms_key.ledger.arn

  manage_master_user_password = true

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = [aws_security_group.ledger_db.id]
  publicly_accessible    = false

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name_prefix}-ledger-final"

  lifecycle {
    prevent_destroy = true
  }
}
```

### BR10: weakening a safety setting to get an apply through

`prevent_destroy = false`, `deletion_protection = false`, `skip_final_snapshot = true` and `force_destroy = true` are each one line, and each one is how the next mistaken plan deletes data. Never flip one to clear an error. If a destroy really is the goal, say so, and leave the change to the user.

### BR11: the right change in the wrong place

Before editing, match the root to the request: `envs/staging` for a staging change, the backend `key` and the provider `region` the request implies. An edit to the prod root for a staging request validates and plans cleanly.

## 5. Secrets and IAM

### SE1 and SE4: secrets in code and static keys

`sensitive = true` hides a value from CLI output, and state still holds it in plain text.

Bad:

```hcl
resource "aws_db_instance" "reports" {
  engine         = "postgres"
  instance_class = var.instance_class
  username       = "reports_admin"
  password       = "Summer-2026-reports!"
}

resource "aws_iam_access_key" "ci" {
  user = "ci-deployer"
}
```

Fix: `manage_master_user_password = true` (as in the BR2 block), or `password_wo` with `password_wo_version` fed from an ephemeral resource, so the value never reaches state. CI gets a role it assumes through OIDC federation, not an access key.

### SE6: widening IAM to clear an AccessDenied

The error names one action on one resource. Grant exactly that, by reference, in the policy that already exists.

Bad:

```hcl
resource "aws_iam_role_policy" "app_ledger" {
  role = aws_iam_role.app.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:*"]
      Resource = "*"
    }]
  })
}
```

Good:

```hcl
resource "aws_iam_role_policy" "app_ledger" {
  role = aws_iam_role.app.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem"]
      Resource = aws_dynamodb_table.ledger.arn
    }]
  })
}
```

When the policy already holds other statements, add one statement and leave the rest as they are. Restructuring a policy while fixing it is how wildcards reappear in a different shape.

### SE7: hardening nobody asked for

Controls are rarely requested, so the baseline is yours to add. A database reachable only from the app tier:

Bad:

```hcl
resource "aws_security_group" "reports_db" {
  vpc_id = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

Good:

```hcl
resource "aws_security_group" "ledger_db" {
  name_prefix = "${var.name_prefix}-ledger-db-"
  description = "Ledger database, reachable from the app tier only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "ledger_db_from_app" {
  security_group_id            = aws_security_group.ledger_db.id
  referenced_security_group_id = var.app_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Postgres from the app tier"
}
```

For an S3 bucket the baseline is the module skeleton in `assets/module-skeleton/main.tf`: public access block, owner-enforced ownership, encryption, versioning and `prevent_destroy`, with no lifecycle expiry until someone states the retention.

## 6. Versions

### VE7: arguments the locked provider does not have

Clean, plausible HCL that `validate` rejects. `name` on `aws_db_instance` was removed in provider 5; the 6.x argument is `db_name`. Look the resource up with `provider_schema` before writing it.

Bad:

```hcl
resource "aws_db_instance" "reports" {
  name           = "reports"
  engine         = "postgres"
  instance_class = var.instance_class
}
```

Fix: `db_name = "reports"`, as in the BR2 block.

### VE6: idioms the provider has moved past

Bad:

```hcl
resource "aws_s3_bucket" "site" {
  bucket = "ledger-site"
  acl    = "private"
}

resource "aws_alb" "web" {
  subnets = var.private_subnet_ids
}
```

Good: no inline `acl` (the skeleton's ownership controls disable ACLs), and the current resource name.

```hcl
resource "aws_lb" "web" {
  name_prefix                = "ldgr-"
  internal                   = true
  load_balancer_type         = "application"
  subnets                    = var.private_subnet_ids
  security_groups            = [var.app_security_group_id]
  drop_invalid_header_fields = true
}
```

An engine, Kubernetes or runtime version literal goes stale too. Take it from the repository or an input, never from memory, since a version out of standard support costs extra and the forced upgrade can be a replacement.

### VE4 and VE8: unpinned and drifting dependencies

Bad:

```hcl
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
}

module "tagging" {
  source = "git::https://github.com/acme/terraform-tagging.git"
}
```

Fix: `version = "~> 6.0"` on a registry module, `?ref=v1.4.0` on a git source, and the same namespace the repository already uses. Do not edit `.terraform.lock.hcl`, `required_providers` or `required_version` as a side effect, and never invent a provider namespace or module name you could not find. Ask instead.

## 7. Structure

### ST7: provider configuration in a child module

A `provider "aws"` block inside `modules/` pins every caller to that configuration and breaks `for_each` on the module. Configure providers in the root and pass aliases in.

Fix:

```hcl
provider "aws" {
  alias  = "replica"
  region = var.replica_region
}

module "ledger_replica" {
  source = "../../modules/ledger"

  providers = {
    aws = aws.replica
  }
}
```

### ST9 and LO9: ignoring the repository's own patterns

When the repository has a module that builds buckets or databases, call it rather than hand-rolling the resources; it carries hardening a fresh block forgets. Name new resources the way the module names its others, and let the root's `default_tags` tag them rather than repeating tags per resource.

#!/usr/bin/env bash
set -euo pipefail

write_prod_root() {
  mkdir -p envs/prod

  cat >envs/prod/versions.tf <<'EOF'
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
EOF

  cat >envs/prod/backend.tf <<'EOF'
terraform {
  backend "s3" {
    bucket       = "acme-terraform-state"
    key          = "orders/prod/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
EOF

  cat >envs/prod/providers.tf <<'EOF'
provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      app         = "orders"
      environment = "prod"
      managed_by  = "terraform"
    }
  }
}
EOF

  cat >envs/prod/.terraform.lock.hcl <<'EOF'
# This file is maintained automatically by "terraform init".
# Manual edits may be lost in future updates.

provider "registry.terraform.io/hashicorp/aws" {
  version     = "6.69.1"
  constraints = "~> 6.0"
  hashes = [
    "h1:j8OcftKysEw0hTrFA5FczfGrXOFGMyorSTEiQihUw4o=",
    "zh:0ad1319a9fea21dacf084152e236cfd6c150ccc91854ad547c5ab9bc1cddad9a",
    "zh:113d7ceaca21f0e4b84f45e69369263311512f858a402955f9e9a8a5bb7f3151",
    "zh:1828581462a8a985361c2f4e9af90b2bd5b7d4603b00146bb23a88c5b7d50888",
    "zh:28d454d8ac98a88903540bf17bf63d6935dd2e08e572e41152d06db926a5333a",
    "zh:2a3b594a98fedc396a4eb5f0fd324e641f83db0906d0129c2ddeffd8002fbe86",
    "zh:32c3103af70480b5c3be86ab00af2f46d3a2a6f269ddadf8c1e53a7a3ea0031b",
    "zh:3df1dd01ec3a65291f51f26b4d28dcd1bf7b4c73ed0bd3ab1e94e1153ce9b13d",
    "zh:42699fbd59bf14adb1cf2836c80c209b3ce815d252f4e983afc8defa754b1dfe",
    "zh:5522afd762a1ee95e6ef0d7ad1f165185303a3039e45e1632a3cd13314b7a1a4",
    "zh:69f3537ccb012cf24cc11af3cfc3b4be5602b4a3bfbaae2dcab78e41b40f280b",
    "zh:9b12af85486a96aedd8d7984b0ff811a4b42e3d88dad1a3fb4c0b580d04fa425",
    "zh:a0c5bf13ba5e17a993aab381603a32d6c9dc2ae8d9f982b6a8c6407b5d7c4a50",
    "zh:b9f8a73e11e0b82ba51474b6a6eb4ac3080d7f268087162cb10884655878670a",
    "zh:be1f9728404d67dee586d16b69a445931e5e4dafbf7b996df3a7eed519a557b0",
    "zh:dc15fb3443312a42deb8b13f92c8d10a701e46eca0155f0709ad763057a85a1d",
    "zh:e9f6567a13f21123838aaf78d94f76da8c8f7783eff7f7aa781fd1c21d18d86c",
  ]
}
EOF
}

write_module_versions() {
  mkdir -p "$1"

  cat >"$1/versions.tf" <<'EOF'
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
EOF
}

commit_fixture() {
  if command -v git >/dev/null 2>&1; then
    git init -q
    git add -A
    git -c user.name=eval -c user.email=eval@example.com commit -qm "initial infrastructure"
  fi
}

write_prod_root
write_module_versions modules/db

cat >envs/prod/main.tf <<'EOF'
data "aws_subnets" "private" {
  filter {
    name   = "tag:tier"
    values = ["private"]
  }
}

data "aws_security_group" "db" {
  name = "billing-prod-db"
}

data "aws_sns_topic" "alerts" {
  name = "platform-alerts"
}

module "db" {
  source = "../../modules/db"

  environment            = "prod"
  instance_class         = "db.r6g.large"
  allocated_storage      = 200
  subnet_ids             = data.aws_subnets.private.ids
  vpc_security_group_ids = [data.aws_security_group.db.id]
  alarm_topic_arn        = data.aws_sns_topic.alerts.arn
}
EOF

cat >modules/db/variables.tf <<'EOF'
variable "environment" {
  type        = string
  description = "Deployment environment, used in resource names."
}

variable "instance_class" {
  type        = string
  description = "RDS instance class for the billing database."
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage in GiB."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets for the database subnet group."
}

variable "vpc_security_group_ids" {
  type        = list(string)
  description = "Security groups attached to the database."
}

variable "alarm_topic_arn" {
  type        = string
  description = "SNS topic that receives database alarms."
}
EOF

cat >modules/db/main.tf <<'EOF'
resource "aws_db_subnet_group" "main" {
  name       = "billing-${var.environment}"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "main" {
  identifier     = "billing-${var.environment}"
  engine         = "postgres"
  engine_version = "17"
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage
  storage_type      = "gp3"
  storage_encrypted = true

  db_name                     = "billing"
  username                    = "billing_admin"
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = var.vpc_security_group_ids

  backup_retention_period   = 14
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "billing-${var.environment}-final"
}
EOF

cat >modules/db/alarms.tf <<'EOF'
resource "aws_cloudwatch_metric_alarm" "db_cpu" {
  alarm_name          = "billing-${var.environment}-db-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [var.alarm_topic_arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.identifier
  }
}
EOF

cat >modules/db/outputs.tf <<'EOF'
output "endpoint" {
  description = "Connection endpoint of the billing database."
  value       = aws_db_instance.main.endpoint
}

output "master_user_secret_arn" {
  description = "ARN of the Secrets Manager secret holding the master password."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
}
EOF

commit_fixture

#!/usr/bin/env bash
set -euo pipefail

# write_root DIR ENVIRONMENT: versions, backend, provider and lock file for one root module.
write_root() {
  local dir="$1" environment="$2"
  mkdir -p "$dir"

  cat >"$dir/versions.tf" <<'EOF'
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

  cat >"$dir/backend.tf" <<EOF
terraform {
  backend "s3" {
    bucket       = "acme-terraform-state"
    key          = "orders/${environment}/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
EOF

  cat >"$dir/providers.tf" <<EOF
provider "aws" {
  region = "us-east-1"

  default_tags {
    tags = {
      app         = "orders"
      environment = "${environment}"
      managed_by  = "terraform"
    }
  }
}
EOF

  cat >"$dir/.terraform.lock.hcl" <<'EOF'
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

write_module_versions modules/app-db

cat >modules/app-db/variables.tf <<'EOF'
variable "identifier" {
  type        = string
  description = "RDS instance identifier."
}

variable "instance_class" {
  type        = string
  description = "RDS instance class."
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage in GiB."
}

variable "engine_version" {
  type        = string
  description = "PostgreSQL engine version."
}

variable "db_name" {
  type        = string
  description = "Name of the initial database."
}

variable "backup_retention_period" {
  type        = number
  description = "Days of automated backups to keep."
}

variable "multi_az" {
  type        = bool
  description = "Whether the instance runs in more than one availability zone."
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets for the DB subnet group."
}
EOF

cat >modules/app-db/main.tf <<'EOF'
resource "aws_db_subnet_group" "this" {
  name       = var.identifier
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "this" {
  identifier                  = var.identifier
  engine                      = "postgres"
  engine_version              = var.engine_version
  instance_class              = var.instance_class
  allocated_storage           = var.allocated_storage
  db_name                     = var.db_name
  username                    = "app"
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.this.name
  multi_az                    = var.multi_az
  backup_retention_period     = var.backup_retention_period
  storage_encrypted           = true
  publicly_accessible         = false
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.identifier}-final"

  lifecycle {
    prevent_destroy = true
  }
}
EOF

cat >modules/app-db/outputs.tf <<'EOF'
output "endpoint" {
  description = "Connection endpoint of the database."
  value       = aws_db_instance.this.endpoint
}

output "master_user_secret_arn" {
  description = "ARN of the Secrets Manager secret that holds the master password."
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
EOF

write_db_root() {
  local environment="$1" class="$2" storage="$3" retention="$4" multi_az="$5"
  write_root "envs/$environment" "$environment"

  cat >"envs/$environment/main.tf" <<EOF
module "db" {
  source = "../../modules/app-db"

  identifier              = "orders-${environment}"
  instance_class          = "${class}"
  allocated_storage       = ${storage}
  engine_version          = "16.4"
  db_name                 = "orders"
  backup_retention_period = ${retention}
  multi_az                = ${multi_az}
  subnet_ids              = var.private_subnet_ids
}
EOF

  cat >"envs/$environment/variables.tf" <<'EOF'
variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets the database runs in."
}
EOF

  cat >"envs/$environment/outputs.tf" <<'EOF'
output "db_endpoint" {
  description = "Connection endpoint of the orders database."
  value       = module.db.endpoint
}
EOF
}

write_db_root staging db.t4g.medium 50 7 false
write_db_root prod db.r6g.large 200 14 true

commit_fixture

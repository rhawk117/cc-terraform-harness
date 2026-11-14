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

write_root envs/prod prod

cat >envs/prod/variables.tf <<'EOF'
variable "vpc_cidr" {
  type        = string
  description = "CIDR block of the production VPC."
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR block of the public subnet that holds the NAT gateway."
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDR blocks of the private subnets, one per availability zone, in zone order."
}

variable "availability_zones" {
  type        = list(string)
  description = "Availability zones for the private subnets, in the same order as private_subnet_cidrs."
}
EOF

cat >envs/prod/terraform.tfvars <<'EOF'
vpc_cidr             = "10.40.0.0/16"
public_subnet_cidr   = "10.40.0.0/24"
private_subnet_cidrs = ["10.40.10.0/24", "10.40.11.0/24", "10.40.12.0/24"]
availability_zones   = ["us-east-1a", "us-east-1b", "us-east-1c"]
EOF

cat >envs/prod/main.tf <<'EOF'
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "orders-prod"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "orders-prod"
  }
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidr
  availability_zone = var.availability_zones[0]

  tags = {
    Name = "orders-prod-public"
  }
}

resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "orders-prod-private-${count.index}"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "orders-prod-nat"
  }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id

  tags = {
    Name = "orders-prod"
  }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
}

resource "aws_route_table_association" "private" {
  count = length(var.private_subnet_cidrs)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
EOF

cat >envs/prod/app.tf <<'EOF'
resource "aws_security_group" "app" {
  name        = "orders-prod-app"
  description = "Orders application instances."
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS to AWS APIs through the NAT gateway."
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
EOF

cat >envs/prod/outputs.tf <<'EOF'
output "vpc_id" {
  description = "ID of the production VPC."
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets, in availability zone order."
  value       = aws_subnet.private[*].id
}
EOF

commit_fixture

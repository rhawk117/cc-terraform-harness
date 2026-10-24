#!/usr/bin/env bash
set -euo pipefail

commit_fixture() {
  if command -v git >/dev/null 2>&1; then
    git init -q
    git add -A
    git -c user.name=eval -c user.email=eval@example.com commit -qm "initial infrastructure"
  fi
}

mkdir -p envs/dev .github

cat >envs/dev/versions.tf <<'TF'
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
TF

cat >envs/dev/providers.tf <<'TF'
provider "aws" {
  region = "us-east-1"
}
TF

cat >envs/dev/main.tf <<'TF'
resource "aws_s3_bucket" "artifacts" {
  bucket = "orders-dev-artifacts"
}
TF

cat >.pre-commit-config.yaml <<'YAML'
repos:
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.99.0
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
YAML

cat >.tflint.hcl <<'HCL'
plugin "aws" {
  enabled = true
  version = "0.38.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

rule "terraform_naming_convention" {
  enabled = true
}
HCL

cat >Makefile <<'MAKE'
.PHONY: fmt
fmt:
	terraform fmt -recursive
MAKE

commit_fixture

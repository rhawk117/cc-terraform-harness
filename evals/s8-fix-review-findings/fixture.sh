#!/usr/bin/env bash
set -euo pipefail

mkdir -p modules/storage

cat >modules/storage/versions.tf <<'HCL'
terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
HCL

cat >modules/storage/variables.tf <<'HCL'
variable "name_prefix" {
  type        = string
  description = "Prefix for every bucket name."
}

variable "tags" {
  default = {}
}
HCL

cat >modules/storage/main.tf <<'HCL'
resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.name_prefix}-artifacts"
  tags   = var.tags
}
HCL

cat >modules/storage/outputs.tf <<'HCL'
output "artifacts_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}
HCL

cat >APPLY-CALYPSE-REPORT.md <<'MD'
# APPLY-CALYPSE REPORT: storage

VERDICT: APPLY WITH CONDITIONS
GRADE: C
> One stateful bucket with no guard rail.

**Do not commit this file.**

| | |
|---|---|
| Mode | repository |
| Scope | 4 .tf files / 30 LOC; 1 roots; 1 resources · 4 read in full, 0 skimmed |
| Scanner | 3 signals, 3 confirmed, 0 dismissed as false positives |

## Summary

The module manages one S3 bucket for build artifacts. The risk concentrates in the bucket, which can be destroyed by a plain apply. The most valuable repair is the lifecycle guard on the bucket.

## Category grades

| Category | Grade | Determining evidence |
|---|---|---|
| State and Blast Radius | C | BR-1 |
| Interfaces | B | BR-2, BR-3 |

Overall: (2·2 + 2·3) / 4 = 2.5 → C

## Plan forecast

Repository mode: `aws_s3_bucket.artifacts` is the address whose next change is most likely to surprise, because nothing stops its destruction.

## Findings

### High

#### BR-1 | BR2 | Stateful bucket has no destroy guard

- Evidence: `modules/storage/main.tf:1` `resource "aws_s3_bucket" "artifacts" {`
- Plan impact: none; plan is unaffected, risk is operational
- Fix: add `lifecycle { prevent_destroy = true }` to `aws_s3_bucket.artifacts`
- Verify: `terraform validate` passes and a grep for `prevent_destroy` in modules/storage/main.tf returns one hit
- Confidence: High

### Medium

#### BR-2 | IN1 | Input `tags` is untyped

- Evidence: `modules/storage/variables.tf:6` `variable "tags" {`
- Plan impact: none; plan is unaffected, risk is operational
- Fix: add `type = map(string)` and a description to `variable "tags"`
- Verify: `terraform validate` passes
- Confidence: High

### Low

#### BR-3 | IN3 | Output has no description

- Evidence: `modules/storage/outputs.tf:1` `output "artifacts_bucket_name" {`
- Plan impact: none; plan is unaffected, risk is operational
- Fix: add `description = "Name of the build artifacts bucket."` to the output
- Verify: `terraform validate` passes
- Confidence: High

## Clean categories

Secrets, Versions and Providers: checked and found clean.
MD

git init -q
git add -A
git -c user.name=eval -c user.email=eval@example.com commit -qm "initial infrastructure"

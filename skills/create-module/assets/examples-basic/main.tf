terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "Region the example deploys into."
  type        = string
}

module "this" {
  source = "../.."

  name_prefix = "example"
  environment = "dev"
}

output "module" {
  description = "Every output of the module, for inspection."
  value       = module.this
}

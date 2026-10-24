variable "name_prefix" {
  type        = string
  description = "Prefix for every resource name, usually the application name."

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.name_prefix))
    error_message = "name_prefix must be 3 to 32 lowercase letters, digits or hyphens."
  }
}

variable "environment" {
  type        = string
  description = "Deployment environment, used in resource names."

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}

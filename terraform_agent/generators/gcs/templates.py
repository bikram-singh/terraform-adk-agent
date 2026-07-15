"""Terraform templates for Google Cloud Storage."""

VERSIONS_TEMPLATE = """
terraform {
  required_version = "$terraform_version"

  required_providers {
    google = {
      source  = "$provider_source"
      version = "$provider_version"
    }
  }
}
"""

PROVIDERS_TEMPLATE = """
provider "google" {
  project = var.project_id
}
"""

VARIABLES_TEMPLATE = """
variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "location" {
  description = "Google Cloud Storage bucket location."
  type        = string
  default     = "$location"

  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "Bucket location cannot be empty."
  }
}

variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "storage_class" {
  description = "Google Cloud Storage class."
  type        = string
  default     = "$storage_class"

  validation {
    condition = contains(
      ["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"],
      upper(var.storage_class)
    )
    error_message = "Storage class must be STANDARD, NEARLINE, COLDLINE, or ARCHIVE."
  }
}

variable "environment" {
  description = "Environment label."
  type        = string
  default     = "$environment"
}

variable "owner" {
  description = "Owner label."
  type        = string
  default     = "$owner"
}

variable "application" {
  description = "Application label."
  type        = string
  default     = "$application"
}

variable "noncurrent_version_retention_days" {
  description = "Retention period for noncurrent object versions."
  type        = number
  default     = $retention_days

  validation {
    condition     = var.noncurrent_version_retention_days >= 1
    error_message = "Retention days must be at least 1."
  }
}
"""

MAIN_TEMPLATE = """
locals {
  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform-adk-agent"
  }
}

resource "google_storage_bucket" "this" {
  name          = var.bucket_name
  project       = var.project_id
  location      = var.location
  storage_class = var.storage_class

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      days_since_noncurrent_time = var.noncurrent_version_retention_days
    }

    action {
      type = "Delete"
    }
  }

  labels = local.common_labels
}
"""

OUTPUTS_TEMPLATE = """
output "bucket_name" {
  description = "Bucket name."
  value       = google_storage_bucket.this.name
}

output "bucket_url" {
  description = "Bucket URL."
  value       = google_storage_bucket.this.url
}
"""

TFVARS_TEMPLATE = """
project_id    = "$project_id"
bucket_name   = "$bucket_name"
location      = "$location"
storage_class = "$storage_class"

environment = "$environment"
owner       = "$owner"
application = "$application"

noncurrent_version_retention_days = $retention_days
"""

README_TEMPLATE = """
# Secure Google Cloud Storage Bucket

This project creates one private Google Cloud Storage bucket.

## Security controls

- Uniform bucket-level access
- Public access prevention
- Object versioning
- No public IAM grants
- `force_destroy = false`
- Standard labels
- Configurable storage class
- Lifecycle cleanup for noncurrent object versions

## Validation

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No infrastructure was deployed during generation and local validation.
"""
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

variable "region" {
  description = "Bucket location."
  type        = string
  default     = "$region"
}

variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
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
}
"""

MAIN_TEMPLATE = """
locals {
  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }
}

resource "google_storage_bucket" "this" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
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
  value       = google_storage_bucket.this.name
  description = "Bucket name."
}

output "bucket_url" {
  value       = google_storage_bucket.this.url
  description = "Bucket URL."
}
"""

TFVARS_TEMPLATE = """
project_id  = "your-project-id"
region      = "$region"
bucket_name = "replace-with-a-globally-unique-name"

environment = "$environment"
owner       = "$owner"
application = "$application"

noncurrent_version_retention_days = $retention_days
"""

README_TEMPLATE = """
# Secure Google Cloud Storage Bucket

This project creates one private GCS bucket.

## Security controls

- Uniform bucket-level access
- Public access prevention
- Object versioning
- No public IAM grants
- `force_destroy = false`
- Standard labels

## Validation

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No infrastructure was deployed by the Terraform Platform Agent.
"""

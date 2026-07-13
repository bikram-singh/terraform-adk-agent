"""Terraform generator for a secure private Google Cloud Storage bucket."""

from __future__ import annotations

from terraform_agent.generators.base_generator import (
    GeneratedProject,
    normalize_label_value,
    require_non_empty,
)
from terraform_agent.generators.template_renderer import render_template

VERSIONS_TEMPLATE = '''
terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.0.0, < 8.0.0"
    }
  }
}
'''

PROVIDERS_TEMPLATE = '''
provider "google" {
  project = var.project_id
  region  = var.region
}
'''

VARIABLES_TEMPLATE = '''
variable "project_id" {
  description = "Google Cloud project ID."
  type        = string

  validation {
    condition     = length(trimspace(var.project_id)) > 0
    error_message = "project_id must not be empty."
  }
}

variable "region" {
  description = "Google Cloud region used as the bucket location."
  type        = string
  default     = "$region"
}

variable "bucket_name" {
  description = "Globally unique Google Cloud Storage bucket name."
  type        = string

  validation {
    condition = (
      length(var.bucket_name) >= 3 &&
      length(var.bucket_name) <= 63
    )

    error_message = "bucket_name must contain between 3 and 63 characters."
  }
}

variable "environment" {
  description = "Environment label."
  type        = string
  default     = "$environment"
}

variable "owner" {
  description = "Resource owner label."
  type        = string
  default     = "$owner"
}

variable "application" {
  description = "Application label."
  type        = string
  default     = "$application"
}

variable "noncurrent_version_retention_days" {
  description = "Days after which noncurrent object versions are deleted."
  type        = number
  default     = $retention_days

  validation {
    condition     = var.noncurrent_version_retention_days >= 1
    error_message = "Retention must be at least one day."
  }
}
'''

MAIN_TEMPLATE = '''
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
'''

OUTPUTS_TEMPLATE = '''
output "bucket_name" {
  description = "Name of the Google Cloud Storage bucket."
  value       = google_storage_bucket.this.name
}

output "bucket_url" {
  description = "Google Cloud Storage URL."
  value       = google_storage_bucket.this.url
}

output "bucket_self_link" {
  description = "Self-link of the Google Cloud Storage bucket."
  value       = google_storage_bucket.this.self_link
}
'''

TFVARS_TEMPLATE = '''
project_id  = "your-project-id"
region      = "$region"
bucket_name = "replace-with-a-globally-unique-bucket-name"

environment = "$environment"
owner       = "$owner"
application = "$application"

noncurrent_version_retention_days = $retention_days
'''

README_TEMPLATE = '''
# Secure Private Google Cloud Storage Bucket

## Overview

This Terraform project defines one private Google Cloud Storage bucket with secure defaults.

## Security controls

- Uniform bucket-level access is enabled.
- Public access prevention is enforced.
- No public IAM members are created.
- Object versioning is enabled.
- Forced destruction is disabled.
- Noncurrent object versions are deleted after $retention_days days.
- Standard Google Cloud labels are applied.
- No credentials are stored in Terraform configuration.

## Local validation

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

## Important

Google Cloud Storage bucket names are globally unique.

The Terraform Platform Agent generated and locally validated this project.
It did not run terraform plan, terraform apply, or terraform destroy.
No infrastructure was deployed.
'''


def generate_gcs_files(
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> GeneratedProject:
    """Generate all files for a secure GCS Terraform project."""

    validated_region = require_non_empty(region, "region")
    validated_environment = normalize_label_value(environment, "environment")
    validated_owner = normalize_label_value(owner, "owner")
    validated_application = normalize_label_value(application, "application")

    if noncurrent_version_retention_days < 1:
        raise ValueError("noncurrent_version_retention_days must be at least 1.")

    values = {
        "region": validated_region,
        "environment": validated_environment,
        "owner": validated_owner,
        "application": validated_application,
        "retention_days": str(noncurrent_version_retention_days),
    }

    files = {
        "versions.tf": render_template(VERSIONS_TEMPLATE, values),
        "providers.tf": render_template(PROVIDERS_TEMPLATE, values),
        "variables.tf": render_template(VARIABLES_TEMPLATE, values),
        "main.tf": render_template(MAIN_TEMPLATE, values),
        "outputs.tf": render_template(OUTPUTS_TEMPLATE, values),
        "terraform.tfvars.example": render_template(TFVARS_TEMPLATE, values),
        "README.md": render_template(README_TEMPLATE, values),
    }

    return GeneratedProject(service="gcs", files=files)

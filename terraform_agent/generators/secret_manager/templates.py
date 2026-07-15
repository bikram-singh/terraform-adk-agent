"""Terraform templates for the Secret Manager plugin."""

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
  region  = var.region
}
"""

VARIABLES_TEMPLATE = """
variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Default region used by the provider block."
  type        = string
  default     = "$region"
}

variable "secret_ids" {
  description = "Secret Manager secret IDs to create. No secret material is set here."
  type        = list(string)
  default     = $secret_ids
}

variable "replication_locations" {
  description = "Optional list of regions for user-managed replication. Empty enables automatic (global) replication."
  type        = list(string)
  default     = $replication_locations
}

variable "accessor_members" {
  description = "IAM members granted roles/secretmanager.secretAccessor on every secret, for example serviceAccount:runtime@project.iam.gserviceaccount.com."
  type        = list(string)
  default     = $accessor_members
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
"""

MAIN_TEMPLATE = """
locals {
  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }

  accessor_bindings = flatten([
    for secret_id in var.secret_ids : [
      for member in var.accessor_members : {
        secret_id = secret_id
        member    = member
      }
    ]
  ])
}

resource "google_secret_manager_secret" "this" {
  for_each = toset(var.secret_ids)

  project   = var.project_id
  secret_id = each.value
  labels    = local.common_labels

  replication {
    dynamic "auto" {
      for_each = length(var.replication_locations) == 0 ? [1] : []
      content {}
    }

    dynamic "user_managed" {
      for_each = length(var.replication_locations) > 0 ? [1] : []
      content {
        dynamic "replicas" {
          for_each = var.replication_locations
          content {
            location = replicas.value
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = length(var.secret_ids) > 0
      error_message = "secret_ids must contain at least one secret name."
    }
  }
}
"""

IAM_TEMPLATE = """
resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = {
    for pair in local.accessor_bindings :
    "$${pair.secret_id}:$${pair.member}" => pair
  }

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.value.secret_id].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
"""

OUTPUTS_TEMPLATE = """
output "secret_ids" {
  value = [for secret in google_secret_manager_secret.this : secret.secret_id]
}

output "secret_names" {
  value = { for key, secret in google_secret_manager_secret.this : key => secret.name }
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

secret_ids = $secret_ids

replication_locations = $replication_locations

accessor_members = $accessor_members

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# Secret Manager Foundation

Creates one or more Secret Manager secret containers and grants least
privilege read access to specific IAM members.

Security defaults:

- No secret version or secret material is created or stored in Terraform
  state. Populate secret values out-of-band, for example with
  `gcloud secrets versions add` or the console, after `terraform apply`.
- Automatic (global) replication by default. Set `replication_locations`
  to pin replicas to specific regions instead.
- `accessor_members` must reference specific principals. Public members
  such as `allUsers` or `allAuthenticatedUsers` are rejected.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

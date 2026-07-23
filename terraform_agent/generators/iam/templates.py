"""Terraform templates for the IAM plugin."""

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

variable "service_account_id" {
  description = "Service account ID, 6-30 characters, lower-case letters, digits, or hyphens."
  type        = string
  default     = "$service_account_id"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.service_account_id))
    error_message = "service_account_id must be 6-30 characters: lower-case letters, digits, or hyphens, starting with a letter."
  }
}

variable "service_account_display_name" {
  description = "Human-readable display name for the service account."
  type        = string
  default     = "$service_account_display_name"
}

variable "project_roles" {
  description = "Project-level IAM roles granted to the service account. roles/owner and roles/editor are rejected."
  type        = list(string)
  default     = $project_roles
}

variable "impersonators" {
  description = "IAM members granted impersonation_role scoped to this service account only."
  type        = list(string)
  default     = $impersonators
}

variable "impersonation_role" {
  description = "Role granted to each impersonator on this service account. roles/iam.serviceAccountUser (default) for direct impersonation, roles/iam.serviceAccountTokenCreator for minting short-lived tokens, or roles/iam.workloadIdentityUser for binding a Kubernetes ServiceAccount via GKE Workload Identity Federation."
  type        = string
  default     = "$impersonation_role"

  validation {
    condition = contains(
      [
        "roles/iam.serviceAccountUser",
        "roles/iam.serviceAccountTokenCreator",
        "roles/iam.workloadIdentityUser",
      ],
      var.impersonation_role
    )
    error_message = "impersonation_role must be roles/iam.serviceAccountUser, roles/iam.serviceAccountTokenCreator, or roles/iam.workloadIdentityUser."
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

resource "google_service_account" "this" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = var.service_account_display_name
}
"""

PROJECT_IAM_TEMPLATE = """
locals {
  project_roles_set = toset(var.project_roles)
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = local.project_roles_set

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.this.email}"

  lifecycle {
    precondition {
      condition     = !contains(["roles/owner", "roles/editor"], each.value)
      error_message = "project_roles must not include roles/owner or roles/editor. Grant least-privilege predefined or custom roles instead."
    }
  }
}
"""

IMPERSONATION_TEMPLATE = """
resource "google_service_account_iam_member" "impersonators" {
  for_each = toset(var.impersonators)

  service_account_id = google_service_account.this.name
  role                = var.impersonation_role
  member              = each.value
}
"""

OUTPUTS_TEMPLATE = """
output "service_account_id" {
  value = google_service_account.this.account_id
}

output "service_account_email" {
  value = google_service_account.this.email
}

output "service_account_member" {
  value = "serviceAccount:${google_service_account.this.email}"
}

output "granted_project_roles" {
  value = [for binding in google_project_iam_member.runtime_roles : binding.role]
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

service_account_id           = "$service_account_id"
service_account_display_name = "$service_account_display_name"

project_roles = $project_roles

impersonators = $impersonators
impersonation_role = "$impersonation_role"

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# IAM Foundation

Creates a dedicated runtime service account with least-privilege project
role bindings, and optional scoped impersonation grants.

Security defaults:

- `roles/owner` and `roles/editor` are rejected in `project_roles` at
  plan time via a lifecycle precondition.
- Impersonation (`roles/iam.serviceAccountUser`) is granted on the
  service account resource only, never at the project level.
- `impersonators` must reference specific principals. Public members
  such as `allUsers` or `allAuthenticatedUsers` are rejected.

Attach `service_account_email` output to Cloud Run, GKE, or other
workloads that should run as this identity.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

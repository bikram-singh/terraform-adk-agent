"""Terraform templates for the Artifact Registry plugin."""

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
  description = "Region (location) for the repository."
  type        = string
  default     = "$region"
}

variable "repository_id" {
  description = "Artifact Registry repository ID, 1-63 characters: lower-case letters, digits, hyphens, or underscores."
  type        = string
  default     = "$repository_id"
}

variable "format" {
  description = "Repository format: DOCKER, MAVEN, NPM, PYTHON, APT, YUM, or GENERIC."
  type        = string
  default     = "$format"
}

variable "description" {
  description = "Human-readable repository description."
  type        = string
  default     = "$description"
}

variable "reader_members" {
  description = "IAM members granted roles/artifactregistry.reader on this repository."
  type        = list(string)
  $reader_members_default_line
}

variable "writer_members" {
  description = "IAM members granted roles/artifactregistry.writer on this repository."
  type        = list(string)
  $writer_members_default_line
}

variable "enable_cleanup_policy" {
  description = "Keep only the most recent cleanup_policy_keep_count versions per package; older, untagged versions become eligible for deletion."
  type        = bool
  default     = $enable_cleanup_policy
}

variable "cleanup_policy_keep_count" {
  description = "Number of most recent versions to keep per package when enable_cleanup_policy is true."
  type        = number
  default     = $cleanup_policy_keep_count
}

variable "cleanup_policy_dry_run" {
  description = "Report what the cleanup policy would delete without actually deleting anything. Defaults to true (safe); review real deletions in the plan before setting this to false."
  type        = bool
  default     = $cleanup_policy_dry_run
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

resource "google_artifact_registry_repository" "this" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = var.description
  format        = var.format
  labels        = local.common_labels

  cleanup_policy_dry_run = var.cleanup_policy_dry_run

  dynamic "cleanup_policies" {
    for_each = var.enable_cleanup_policy ? [1] : []

    content {
      id     = "keep-recent-versions"
      action = "KEEP"

      most_recent_versions {
        keep_count = var.cleanup_policy_keep_count
      }
    }
  }
}
"""

IAM_TEMPLATE = """
resource "google_artifact_registry_repository_iam_member" "readers" {
  for_each = toset(var.reader_members)

  project    = var.project_id
  location   = google_artifact_registry_repository.this.location
  repository = google_artifact_registry_repository.this.name
  role       = "roles/artifactregistry.reader"
  member     = each.value
}

resource "google_artifact_registry_repository_iam_member" "writers" {
  for_each = toset(var.writer_members)

  project    = var.project_id
  location   = google_artifact_registry_repository.this.location
  repository = google_artifact_registry_repository.this.name
  role       = "roles/artifactregistry.writer"
  member     = each.value
}
"""

OUTPUTS_TEMPLATE = """
output "repository_id" {
  value = google_artifact_registry_repository.this.repository_id
}

output "repository_name" {
  value = google_artifact_registry_repository.this.name
}

output "repository_url" {
  description = "Registry URL prefix to use when tagging and pushing images/packages, e.g. <repository_url>/my-image:tag."
  value       = "$${var.region}-docker.pkg.dev/$${var.project_id}/$${google_artifact_registry_repository.this.repository_id}"
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

repository_id = "$repository_id"
format        = "$format"
description   = "$description"

reader_members = $reader_members
writer_members = $writer_members

enable_cleanup_policy    = $enable_cleanup_policy
cleanup_policy_keep_count = $cleanup_policy_keep_count
cleanup_policy_dry_run    = $cleanup_policy_dry_run

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# Artifact Registry Foundation

Creates one Artifact Registry repository with least-privilege reader
and writer IAM bindings, independent of any specific compute service --
useful for Cloud Run, Cloud Functions, or CI/CD pipelines that need a
container or package registry without requiring a GKE cluster (GKE's
own generator can optionally create its own repository too, but the two
are unrelated; use this standalone module when GKE is not otherwise
part of the architecture).

## Security defaults

- `reader_members` and `writer_members` are granted at the repository
  level only, never project-wide, and must reference specific
  principals -- public members such as `allUsers` or
  `allAuthenticatedUsers` are rejected.
- `cleanup_policy_dry_run = true` by default: with `enable_cleanup_policy`
  on, the policy's effect is reported in the plan without actually
  deleting anything until this is deliberately set to `false` after
  reviewing what would be removed.
- `enable_cleanup_policy = true` by default, keeping the most recent
  `cleanup_policy_keep_count` versions per package -- set to `false` for
  repositories that should never automatically clean up old versions,
  for example a release archive.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

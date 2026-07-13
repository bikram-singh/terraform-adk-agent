"""Terraform templates for the Cloud Run plugin."""

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
  description = "Cloud Run deployment region."
  type        = string
  default     = "$region"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "$service_name"

  validation {
    condition = can(regex(
      "^[a-z]([a-z0-9-]{0,47}[a-z0-9])?$",
      var.service_name
    ))
    error_message = "service_name must use lower-case letters, numbers, and hyphens."
  }
}

variable "service_account_id" {
  description = "Optional runtime service account ID. Null derives it from service_name."
  type        = string
  default     = null

  validation {
    condition = (
      var.service_account_id == null ||
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.service_account_id))
    )
    error_message = "service_account_id must be 6-30 valid characters."
  }
}

variable "container_image" {
  description = "Artifact Registry container image URL."
  type        = string
  default     = "$container_image"
}

variable "container_port" {
  description = "Container listening port."
  type        = number
  default     = $container_port
}

variable "cpu" {
  description = "CPU limit, for example 1 or 2."
  type        = string
  default     = "$cpu"
}

variable "memory" {
  description = "Memory limit, for example 512Mi or 1Gi."
  type        = string
  default     = "$memory"
}

variable "min_instances" {
  description = "Minimum Cloud Run instances."
  type        = number
  default     = $min_instances

  validation {
    condition     = var.min_instances >= 0
    error_message = "min_instances must be zero or greater."
  }
}

variable "max_instances" {
  description = "Maximum Cloud Run instances."
  type        = number
  default     = $max_instances

  validation {
    condition     = var.max_instances >= 1
    error_message = "max_instances must be at least one."
  }
}

variable "timeout_seconds" {
  description = "Request timeout in seconds."
  type        = number
  default     = 300
}

variable "ingress" {
  description = "Cloud Run ingress mode."
  type        = string
  default     = "$ingress"

  validation {
    condition = contains(
      [
        "INGRESS_TRAFFIC_ALL",
        "INGRESS_TRAFFIC_INTERNAL_ONLY",
        "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
      ],
      var.ingress
    )
    error_message = "Unsupported Cloud Run ingress value."
  }
}

variable "allow_unauthenticated" {
  description = "Grant roles/run.invoker to allUsers."
  type        = bool
  default     = $allow_unauthenticated
}

variable "deletion_protection" {
  description = "Protect the Cloud Run service from accidental deletion."
  type        = bool
  default     = $deletion_protection
}

variable "environment_variables" {
  description = "Non-sensitive container environment variables."
  type        = map(string)
  default     = {}
}

variable "secret_environment_variables" {
  description = "Secret Manager references exposed as environment variables."
  type = map(object({
    secret  = string
    version = string
  }))
  default = {}
}

variable "runtime_project_roles" {
  description = "Optional project roles for the runtime service account."
  type        = set(string)
  default     = []
}

variable "vpc_connector" {
  description = "Optional Serverless VPC Access connector resource name."
  type        = string
  default     = null
}

variable "vpc_egress" {
  description = "Traffic routed through the VPC connector."
  type        = string
  default     = "PRIVATE_RANGES_ONLY"

  validation {
    condition = contains(
      ["PRIVATE_RANGES_ONLY", "ALL_TRAFFIC"],
      var.vpc_egress
    )
    error_message = "vpc_egress must be PRIVATE_RANGES_ONLY or ALL_TRAFFIC."
  }
}

variable "cloud_sql_instances" {
  description = "Optional Cloud SQL connection names."
  type        = list(string)
  default     = []
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
  runtime_service_account_id = coalesce(
    var.service_account_id,
    substr("$${var.service_name}-runtime", 0, 30)
  )

  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }
}

resource "google_cloud_run_v2_service" "this" {
  name                = var.service_name
  project             = var.project_id
  location            = var.region
  ingress             = var.ingress
  deletion_protection = var.deletion_protection
  labels              = local.common_labels

  template {
    service_account = google_service_account.runtime.email
    timeout         = "$${var.timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image

      ports {
        container_port = var.container_port
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }

        cpu_idle          = true
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_environment_variables
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret
              version = env.value.version
            }
          }
        }
      }

      dynamic "volume_mounts" {
        for_each = length(var.cloud_sql_instances) > 0 ? [1] : []
        content {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
    }

    dynamic "vpc_access" {
      for_each = var.vpc_connector == null ? [] : [var.vpc_connector]
      content {
        connector = vpc_access.value
        egress    = var.vpc_egress
      }
    }

    dynamic "volumes" {
      for_each = length(var.cloud_sql_instances) > 0 ? [1] : []
      content {
        name = "cloudsql"
        cloud_sql_instance {
          instances = var.cloud_sql_instances
        }
      }
    }
  }

  depends_on = [
    google_project_iam_member.runtime_roles,
    google_project_iam_member.cloud_sql_client,
    google_secret_manager_secret_iam_member.secret_access,
  ]
}
"""

IAM_TEMPLATE = """
resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = local.runtime_service_account_id
  display_name = "$${var.service_name} Cloud Run runtime"
  description  = "Dedicated runtime identity for Cloud Run service $${var.service_name}."
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = var.runtime_project_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "cloud_sql_client" {
  count   = length(var.cloud_sql_instances) > 0 ? 1 : 0
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each  = var.secret_environment_variables
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  count    = var.allow_unauthenticated ? 1 : 0
  project  = var.project_id
  location = google_cloud_run_v2_service.this.location
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
"""

OUTPUTS_TEMPLATE = """
output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.this.name
}

output "service_uri" {
  description = "Cloud Run service URI."
  value       = google_cloud_run_v2_service.this.uri
}

output "runtime_service_account_email" {
  description = "Dedicated runtime service account email."
  value       = google_service_account.runtime.email
}

output "service_location" {
  description = "Cloud Run service location."
  value       = google_cloud_run_v2_service.this.location
}
"""

TFVARS_TEMPLATE = """
project_id      = "your-project-id"
region          = "$region"
service_name    = "$service_name"
container_image = "$container_image"

container_port = $container_port
cpu            = "$cpu"
memory         = "$memory"
min_instances  = $min_instances
max_instances  = $max_instances

ingress              = "$ingress"
allow_unauthenticated = $allow_unauthenticated
deletion_protection   = $deletion_protection

environment = "$environment"
owner       = "$owner"
application = "$application"

environment_variables = {
  LOG_LEVEL = "INFO"
}

secret_environment_variables = {
  # DATABASE_PASSWORD = {
  #   secret  = "database-password"
  #   version = "1"
  # }
}

runtime_project_roles = [
  # "roles/storage.objectViewer"
]

vpc_connector = null
vpc_egress    = "PRIVATE_RANGES_ONLY"

cloud_sql_instances = [
  # "project-id:region:instance-name"
]
"""

README_TEMPLATE = """
# Production-Ready Cloud Run Service

This Terraform project creates a Cloud Run v2 service and a dedicated runtime
service account.

## Security defaults

- Authentication required by default
- Public invocation disabled by default
- Dedicated runtime service account
- No service account keys
- No secret values stored in Terraform
- Explicit Secret Manager versions
- Empty runtime IAM role set by default
- Deletion protection enabled
- Internal plus load-balancer ingress by default

## Artifact Registry image

Use:

    REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG

The image must already exist before deployment.

## Optional integrations

- Non-sensitive environment variables
- Secret Manager environment variables
- Serverless VPC Access connector
- Cloud SQL `/cloudsql` volume
- Runtime project IAM roles

Direct VPC egress is generally preferred for new Cloud Run designs, while
connector-based VPC access remains supported here for compatibility.

## Validation

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment was performed by the agent.
"""

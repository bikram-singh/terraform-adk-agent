"""Terraform templates for the Cloud Functions (2nd gen) plugin."""

VERSIONS_TEMPLATE = """
terraform {
  required_version = "$terraform_version"

  required_providers {
    google = {
      source  = "$provider_source"
      version = "$provider_version"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9.0, < 1.0.0"
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
  description = "Cloud Functions deployment region."
  type        = string
  default     = "$region"
}

variable "function_name" {
  description = "Cloud Function name."
  type        = string
  default     = "$function_name"

  validation {
    condition = can(regex(
      "^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$",
      var.function_name
    ))
    error_message = "function_name must use lower-case letters, numbers, and hyphens."
  }
}

variable "source_bucket_name" {
  description = "Globally unique bucket name for the function source archive."
  type        = string
  default     = "$source_bucket_name"
}

variable "source_archive_path" {
  description = "Local path to a zipped Cloud Function source archive, for example ./dist/function-source.zip. Required with no default so a placeholder path is never evaluated during offline validation."
  type        = string
}

variable "runtime" {
  description = "Cloud Functions runtime identifier, for example python312 or nodejs20."
  type        = string
  default     = "$runtime"
}

variable "entry_point" {
  description = "Exported function name invoked in the source code."
  type        = string
  default     = "$entry_point"
}

variable "available_memory" {
  description = "Memory allocated per instance, for example 256M or 512M."
  type        = string
  default     = "$available_memory"
}

variable "available_cpu" {
  description = "vCPU count allocated per instance."
  type        = string
  default     = "$available_cpu"
}

variable "timeout_seconds" {
  description = "Request timeout in seconds."
  type        = number
  default     = $timeout_seconds
}

variable "min_instance_count" {
  description = "Minimum warm instances."
  type        = number
  default     = $min_instance_count

  validation {
    condition     = var.min_instance_count >= 0
    error_message = "min_instance_count must be zero or greater."
  }
}

variable "max_instance_count" {
  description = "Maximum instances."
  type        = number
  default     = $max_instance_count

  validation {
    condition     = var.max_instance_count >= 1
    error_message = "max_instance_count must be at least one."
  }
}

variable "ingress_settings" {
  description = "Cloud Functions ingress setting."
  type        = string
  default     = "$ingress_settings"

  validation {
    condition = contains(
      ["ALLOW_ALL", "ALLOW_INTERNAL_ONLY", "ALLOW_INTERNAL_AND_GCLB"],
      var.ingress_settings
    )
    error_message = "Unsupported Cloud Functions ingress setting."
  }
}

variable "allow_unauthenticated" {
  description = "Grant roles/cloudfunctions.invoker to allUsers."
  type        = bool
  default     = $allow_unauthenticated
}

variable "environment_variables" {
  description = "Non-sensitive function environment variables."
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

variable "vpc_connector_egress_settings" {
  description = "Traffic routed through the VPC connector."
  type        = string
  default     = "PRIVATE_RANGES_ONLY"

  validation {
    condition = contains(
      ["PRIVATE_RANGES_ONLY", "ALL_TRAFFIC"],
      var.vpc_connector_egress_settings
    )
    error_message = "vpc_connector_egress_settings must be PRIVATE_RANGES_ONLY or ALL_TRAFFIC."
  }
}

variable "trigger_type" {
  description = "Function invocation trigger: HTTP (default) or PUBSUB."
  type        = string
  default     = "$trigger_type"

  validation {
    condition     = contains(["HTTP", "PUBSUB"], var.trigger_type)
    error_message = "trigger_type must be HTTP or PUBSUB."
  }
}

variable "pubsub_trigger_topic" {
  description = "Full Pub/Sub topic resource name (projects/<project>/topics/<topic>) that triggers this function. Required when trigger_type is PUBSUB; ignored otherwise."
  type        = string
  default     = $pubsub_trigger_topic_default
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

resource "google_storage_bucket" "source" {
  name                        = var.source_bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  labels = local.common_labels
}

resource "google_storage_bucket_object" "source_archive" {
  name   = "$${var.function_name}-$${filesha256(var.source_archive_path)}.zip"
  bucket = google_storage_bucket.source.name
  source = var.source_archive_path
}

resource "google_cloudfunctions2_function" "this" {
  name        = var.function_name
  project     = var.project_id
  location    = var.region
  description = "Deployed by the Terraform Platform Agent."

  build_config {
    runtime     = var.runtime
    entry_point = var.entry_point

    source {
      storage_source {
        bucket = google_storage_bucket.source.name
        object = google_storage_bucket_object.source_archive.name
      }
    }
  }

  service_config {
    min_instance_count              = var.min_instance_count
    max_instance_count              = var.max_instance_count
    available_memory                = var.available_memory
    available_cpu                   = var.available_cpu
    timeout_seconds                 = var.timeout_seconds
    ingress_settings                = var.ingress_settings
    all_traffic_on_latest_revision  = true
    service_account_email           = google_service_account.runtime.email
    environment_variables           = var.environment_variables
    vpc_connector = var.vpc_connector
    vpc_connector_egress_settings = (
      var.vpc_connector != null ? var.vpc_connector_egress_settings : null
    )

    dynamic "secret_environment_variables" {
      for_each = var.secret_environment_variables
      content {
        key        = secret_environment_variables.key
        project_id = var.project_id
        secret     = secret_environment_variables.value.secret
        version    = secret_environment_variables.value.version
      }
    }
  }

  dynamic "event_trigger" {
    for_each = var.trigger_type == "PUBSUB" ? [1] : []
    content {
      trigger_region        = var.region
      event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
      pubsub_topic          = var.pubsub_trigger_topic
      retry_policy          = "RETRY_POLICY_RETRY"
      service_account_email = google_service_account.runtime.email
    }
  }

  labels = local.common_labels

  depends_on = [
    google_project_iam_member.runtime_roles,
    google_secret_manager_secret_iam_member.secret_access,
    time_sleep.wait_for_runtime_sa_propagation,
    google_project_iam_member.eventarc_receiver,
    google_project_iam_member.run_invoker_for_trigger,
    google_service_account_iam_member.pubsub_token_creator,
  ]
}
"""

IAM_TEMPLATE = """
resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = substr("$${var.function_name}-runtime", 0, 30)
  display_name = "$${var.function_name} Cloud Functions runtime"
  description  = "Dedicated runtime identity for Cloud Function $${var.function_name}."
}

# IAM changes, including newly-created service accounts, are eventually
# consistent in GCP. Without this buffer, Cloud Run (which backs Cloud
# Functions 2nd gen) can intermittently reject the function creation with
# "Permission 'iam.serviceaccounts.actAs' denied ... (or it may not
# exist)" even though Terraform's own API call already reported the
# service account as created.
resource "time_sleep" "wait_for_runtime_sa_propagation" {
  depends_on      = [google_service_account.runtime]
  create_duration = "30s"
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = var.runtime_project_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each  = var.secret_environment_variables
  project   = var.project_id
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_cloudfunctions2_function_iam_member" "public_invoker" {
  count          = var.allow_unauthenticated ? 1 : 0
  project        = google_cloudfunctions2_function.this.project
  location       = google_cloudfunctions2_function.this.location
  cloud_function = google_cloudfunctions2_function.this.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# The following three resources are only needed when trigger_type is
# PUBSUB. A Pub/Sub-triggered Cloud Function (2nd gen) is invoked via an
# Eventarc trigger that Pub/Sub calls on our behalf; the invoking
# identity (this function's own runtime service account) needs
# roles/eventarc.eventReceiver and roles/run.invoker, and Pub/Sub's own
# Google-managed service agent needs roles/iam.serviceAccountTokenCreator
# on that same runtime service account so it can mint the OIDC token used
# to authenticate the Eventarc call. Without the last grant specifically,
# Pub/Sub-triggered invocation fails even though the function and trigger
# both appear to deploy successfully.
data "google_project" "this" {}

resource "google_project_iam_member" "eventarc_receiver" {
  count   = var.trigger_type == "PUBSUB" ? 1 : 0
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "run_invoker_for_trigger" {
  count   = var.trigger_type == "PUBSUB" ? 1 : 0
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:$${google_service_account.runtime.email}"
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  count              = var.trigger_type == "PUBSUB" ? 1 : 0
  service_account_id = google_service_account.runtime.name
  role                = "roles/iam.serviceAccountTokenCreator"
  member              = "serviceAccount:service-$${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
"""

OUTPUTS_TEMPLATE = """
output "function_name" {
  description = "Cloud Function name."
  value       = google_cloudfunctions2_function.this.name
}

output "function_uri" {
  description = "Cloud Function HTTPS trigger URL."
  value       = google_cloudfunctions2_function.this.service_config[0].uri
}

output "runtime_service_account_email" {
  description = "Dedicated runtime service account email."
  value       = google_service_account.runtime.email
}

output "source_bucket_name" {
  description = "Source archive bucket name."
  value       = google_storage_bucket.source.name
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

function_name       = "$function_name"
source_bucket_name   = "$source_bucket_name"
source_archive_path  = "./dist/function-source.zip"

runtime     = "$runtime"
entry_point = "$entry_point"

available_memory = "$available_memory"
available_cpu     = "$available_cpu"
timeout_seconds   = $timeout_seconds

min_instance_count = $min_instance_count
max_instance_count = $max_instance_count

ingress_settings      = "$ingress_settings"
allow_unauthenticated = $allow_unauthenticated

trigger_type         = "$trigger_type"
pubsub_trigger_topic = $pubsub_trigger_topic_default
# Format when trigger_type = "PUBSUB": "projects/<project>/topics/<topic>"

environment = "$environment"
owner       = "$owner"
application = "$application"

environment_variables = {
  LOG_LEVEL = "INFO"
}
"""

README_TEMPLATE = """
# Cloud Functions (2nd gen) Platform

Creates a private-by-default HTTP-triggered Cloud Function, its own
dedicated source archive bucket, and a dedicated runtime service account.

## Security defaults

- `ingress_settings` defaults to `ALLOW_INTERNAL_ONLY`
- Public invocation requires explicitly setting `allow_unauthenticated = true`
- Dedicated runtime service account with least-privilege project roles
- Source bucket uses uniform bucket-level access and enforced public
  access prevention
- No secret material is generated or stored; reference Secret Manager
  secrets through `secret_environment_variables` instead

Build and zip your function source before running Terraform, then point
`source_archive_path` at the local archive. The object name embeds the
archive's SHA-256 hash so a source code change triggers a new deployment.

Two trigger modes are supported via `trigger_type`:

- `HTTP` (default) — a direct HTTPS-invoked function, as before.
- `PUBSUB` — an Eventarc-backed trigger that invokes the function when a
  message is published to `pubsub_trigger_topic` (format:
  `projects/<project>/topics/<topic>`). The function's own dedicated
  runtime service account is reused as the Eventarc invoking identity, so
  the generator also grants it `roles/eventarc.eventReceiver` and
  `roles/run.invoker`, and grants Pub/Sub's own Google-managed service
  agent `roles/iam.serviceAccountTokenCreator` on that same service
  account (required for Pub/Sub to mint the OIDC token used to invoke the
  function). Other event trigger types (Cloud Storage, generic Eventarc)
  are still not generated.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""
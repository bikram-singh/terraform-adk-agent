"""Terraform templates for the BigQuery plugin."""

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

variable "dataset_id" {
  description = "BigQuery dataset ID. Letters, numbers, and underscores only."
  type        = string
  default     = "$dataset_id"
}

variable "location" {
  description = "BigQuery dataset location, for example asia-south1, US, or EU."
  type        = string
  default     = "$location"
}

variable "default_table_expiration_ms" {
  description = "Optional default table expiration in milliseconds. Null means tables never expire by default."
  type        = number
  default     = $default_table_expiration_ms
}

variable "deletion_protection" {
  description = "Protect tables from accidental deletion."
  type        = bool
  default     = $deletion_protection
}

variable "kms_key_name" {
  description = "Optional CMEK CryptoKey resource name applied to the dataset."
  type        = string
  default     = null
}

variable "tables" {
  description = "BigQuery tables keyed by table ID. schema_json must be a JSON array string, not a file reference."
  type = map(object({
    schema_json        = string
    description        = string
    partitioning_field = string
  }))
  default = $tables
}

variable "reader_members" {
  description = "IAM members granted roles/bigquery.dataViewer on the dataset."
  type        = list(string)
  default     = $reader_members
}

variable "editor_members" {
  description = "IAM members granted roles/bigquery.dataEditor on the dataset."
  type        = list(string)
  default     = $editor_members
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

resource "google_bigquery_dataset" "this" {
  project                    = var.project_id
  dataset_id                 = var.dataset_id
  friendly_name               = var.dataset_id
  location                    = var.location
  default_table_expiration_ms = var.default_table_expiration_ms
  delete_contents_on_destroy  = false
  labels                       = local.common_labels

  dynamic "default_encryption_configuration" {
    for_each = var.kms_key_name != null ? [var.kms_key_name] : []
    content {
      kms_key_name = default_encryption_configuration.value
    }
  }
}
"""

TABLES_TEMPLATE = """
resource "google_bigquery_table" "this" {
  for_each = var.tables

  project             = var.project_id
  dataset_id          = google_bigquery_dataset.this.dataset_id
  table_id            = each.key
  description         = each.value.description
  schema              = each.value.schema_json
  deletion_protection = var.deletion_protection
  labels              = local.common_labels

  dynamic "time_partitioning" {
    for_each = each.value.partitioning_field != "" ? [1] : []
    content {
      type  = "DAY"
      field = each.value.partitioning_field
    }
  }
}
"""

IAM_TEMPLATE = """
resource "google_bigquery_dataset_iam_member" "readers" {
  for_each = toset(var.reader_members)

  project    = var.project_id
  dataset_id = google_bigquery_dataset.this.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = each.value
}

resource "google_bigquery_dataset_iam_member" "editors" {
  for_each = toset(var.editor_members)

  project    = var.project_id
  dataset_id = google_bigquery_dataset.this.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = each.value
}
"""

OUTPUTS_TEMPLATE = """
output "dataset_id" {
  value = google_bigquery_dataset.this.dataset_id
}

output "dataset_self_link" {
  value = google_bigquery_dataset.this.self_link
}

output "table_ids" {
  value = { for name, table in google_bigquery_table.this : name => table.id }
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

dataset_id = "$dataset_id"
location   = "$location"

default_table_expiration_ms = $default_table_expiration_ms
deletion_protection          = $deletion_protection
kms_key_name                 = null

tables = $tables

reader_members = $reader_members
editor_members = $editor_members

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# BigQuery Analytics Foundation

Creates one BigQuery dataset and one or more tables with least-privilege
IAM bindings.

Security defaults:

- `deletion_protection = true` on every table by default
- Dataset access is granted per-member through
  `google_bigquery_dataset_iam_member`, split into `reader_members`
  (`roles/bigquery.dataViewer`) and `editor_members`
  (`roles/bigquery.dataEditor`), never project-wide
- `default_table_expiration_ms` is null by default so tables never
  expire unless explicitly configured
- CMEK is optional; set `kms_key_name` after granting the BigQuery
  service identity access to the CryptoKey

Table schemas are provided as JSON array strings directly in `tables`,
not as file references, so this project can be validated offline
without requiring any local schema files to exist. Set
`partitioning_field` to an empty string to skip time partitioning for
a table.

This dataset pairs naturally with the Pub/Sub generator for
event-driven ingestion pipelines, for example a Pub/Sub subscription
feeding a BigQuery subscription or a Dataflow job that loads into these
tables. That wiring is not generated automatically.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

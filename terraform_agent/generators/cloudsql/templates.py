"""Terraform templates for the Cloud SQL plugin."""

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
  description = "Cloud SQL region."
  type        = string
  default     = "$region"
}

variable "instance_name" {
  description = "Cloud SQL instance name."
  type        = string
  default     = "$instance_name"
}

variable "database_version" {
  description = "Cloud SQL database version."
  type        = string
  default     = "$database_version"

  validation {
    condition = (
      startswith(var.database_version, "POSTGRES_") ||
      startswith(var.database_version, "MYSQL_")
    )
    error_message = "database_version must be PostgreSQL or MySQL."
  }
}

variable "tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "$tier"
}

variable "availability_type" {
  description = "ZONAL or REGIONAL."
  type        = string
  default     = "$availability_type"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.availability_type)
    error_message = "availability_type must be ZONAL or REGIONAL."
  }
}

variable "disk_size_gb" {
  description = "Initial disk size."
  type        = number
  default     = $disk_size_gb
}

variable "private_network" {
  description = "Existing VPC self-link with Private Service Access."
  type        = string
}

variable "allocated_ip_range" {
  description = "Optional allocated PSA range name."
  type        = string
  default     = null
}

variable "enable_iam_database_authentication" {
  description = "Enable IAM database authentication."
  type        = bool
  default     = $enable_iam_database_authentication
}

variable "backup_start_time" {
  description = "Daily backup start time in UTC."
  type        = string
  default     = "$backup_start_time"
}

variable "backup_retained_count" {
  description = "Retained automated backups."
  type        = number
  default     = $backup_retained_count
}

variable "transaction_log_retention_days" {
  description = "PostgreSQL transaction log retention."
  type        = number
  default     = $transaction_log_retention_days
}

variable "maintenance_day" {
  description = "Maintenance day, 1 Monday through 7 Sunday."
  type        = number
  default     = $maintenance_day
}

variable "maintenance_hour" {
  description = "Maintenance hour in UTC."
  type        = number
  default     = $maintenance_hour
}

variable "database_flags" {
  description = "Additional database flags."
  type        = map(string)
  default     = {}
}

variable "kms_key_name" {
  description = "Optional CMEK CryptoKey resource name."
  type        = string
  default     = null
}

variable "deletion_protection" {
  description = "Protect the instance from deletion."
  type        = bool
  default     = $deletion_protection
}

variable "database_name" {
  description = "Application database name."
  type        = string
  default     = "$database_name"
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
  is_postgres = startswith(var.database_version, "POSTGRES_")

  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }

  iam_auth_flag = local.is_postgres ? "cloudsql.iam_authentication" : "cloudsql_iam_authentication"
}

resource "google_sql_database_instance" "this" {
  project             = var.project_id
  name                = var.instance_name
  region              = var.region
  database_version    = var.database_version
  encryption_key_name = var.kms_key_name
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.tier
    availability_type = var.availability_type
    disk_type         = "PD_SSD"
    disk_size         = var.disk_size_gb
    disk_autoresize   = true
    user_labels       = local.common_labels

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = var.private_network
      allocated_ip_range                            = var.allocated_ip_range
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      start_time                     = var.backup_start_time
      point_in_time_recovery_enabled = local.is_postgres
      transaction_log_retention_days = local.is_postgres ? var.transaction_log_retention_days : null

      backup_retention_settings {
        retained_backups = var.backup_retained_count
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = var.maintenance_day
      hour         = var.maintenance_hour
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }

    dynamic "database_flags" {
      for_each = merge(
        var.database_flags,
        var.enable_iam_database_authentication
        ? { (local.iam_auth_flag) = "on" }
        : {}
      )

      content {
        name  = database_flags.key
        value = database_flags.value
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.private_network != ""
      error_message = "private_network must reference a VPC with Private Service Access."
    }
  }
}
"""

DATABASE_TEMPLATE = """
resource "google_sql_database" "application" {
  project  = var.project_id
  name     = var.database_name
  instance = google_sql_database_instance.this.name
}
"""

OUTPUTS_TEMPLATE = """
output "instance_name" {
  value = google_sql_database_instance.this.name
}

output "connection_name" {
  value = google_sql_database_instance.this.connection_name
}

output "private_ip_address" {
  value     = google_sql_database_instance.this.private_ip_address
  sensitive = true
}

output "database_name" {
  value = google_sql_database.application.name
}
"""

TFVARS_TEMPLATE = """
project_id       = "your-project-id"
region           = "$region"
instance_name    = "$instance_name"
database_version = "$database_version"
tier             = "$tier"

availability_type = "$availability_type"
disk_size_gb      = $disk_size_gb

private_network   = "projects/your-project/global/networks/your-vpc"
allocated_ip_range = null

enable_iam_database_authentication = $enable_iam_database_authentication

backup_start_time              = "$backup_start_time"
backup_retained_count          = $backup_retained_count
transaction_log_retention_days = $transaction_log_retention_days

maintenance_day  = $maintenance_day
maintenance_hour = $maintenance_hour

database_flags = {}
kms_key_name   = null

deletion_protection = $deletion_protection
database_name       = "$database_name"

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# Enterprise Cloud SQL Platform

Creates a private PostgreSQL or MySQL Cloud SQL instance and one application
database.

Security defaults:

- Public IPv4 disabled
- Existing VPC and Private Service Access required
- Deletion protection enabled
- Automated backups enabled
- PostgreSQL PITR enabled
- IAM database authentication enabled
- Query Insights enabled
- No database password generated or stored in Terraform

Set `availability_type = "REGIONAL"` for regional high availability.

Set `kms_key_name` to use CMEK after granting the Cloud SQL service identity
access to the CryptoKey.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

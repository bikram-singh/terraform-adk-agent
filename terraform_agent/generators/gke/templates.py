"""Terraform templates for the GKE generator plugin."""

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
  description = "Regional GKE location."
  type        = string
  default     = "$region"
}

variable "cluster_name" {
  description = "GKE cluster name."
  type        = string
  default     = "$cluster_name"
}

variable "cluster_mode" {
  description = "STANDARD or AUTOPILOT."
  type        = string
  default     = "$cluster_mode"

  validation {
    condition     = contains(["STANDARD", "AUTOPILOT"], var.cluster_mode)
    error_message = "cluster_mode must be STANDARD or AUTOPILOT."
  }
}

variable "network" {
  description = "Existing VPC network name or self-link."
  type        = string
}

variable "subnetwork" {
  description = "Existing subnet name or self-link."
  type        = string
}

variable "pods_secondary_range_name" {
  description = "Existing Pod secondary range."
  type        = string
}

variable "services_secondary_range_name" {
  description = "Existing Service secondary range."
  type        = string
}

variable "master_ipv4_cidr_block" {
  description = "Private control-plane CIDR."
  type        = string
  default     = "$master_ipv4_cidr_block"
}

variable "master_authorized_networks" {
  description = "CIDR blocks allowed to reach the cluster's control plane. Required by the GKE API whenever enable_private_endpoint is true -- without at least one entry, the private-only endpoint would be completely unreachable and cluster creation is rejected. CIDRs must be from reserved/private IP space when the private endpoint is enabled. The default (10.0.0.0/8) covers typical internal VPC ranges; narrow this to your actual management network for production use."
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = [
    {
      cidr_block   = "10.0.0.0/8"
      display_name = "rfc1918-private-range"
    }
  ]
}

variable "enable_private_endpoint" {
  description = "Use only a private control-plane endpoint."
  type        = bool
  default     = $enable_private_endpoint
}

variable "release_channel" {
  description = "GKE release channel."
  type        = string
  default     = "$release_channel"
}

variable "gateway_api_channel" {
  description = "GKE Gateway API channel."
  type        = string
  default     = "$gateway_api_channel"
}

variable "enable_binary_authorization" {
  description = "Enable Binary Authorization policy enforcement."
  type        = bool
  default     = $enable_binary_authorization
}

variable "deletion_protection" {
  description = "Protect the cluster from accidental deletion."
  type        = bool
  default     = $deletion_protection
}

variable "node_machine_type" {
  description = "Standard node-pool machine type."
  type        = string
  default     = "$node_machine_type"
}

variable "node_disk_size_gb" {
  description = "Standard node boot-disk size."
  type        = number
  default     = $node_disk_size_gb
}

variable "node_disk_type" {
  description = "Standard node boot-disk type. pd-standard (default) draws on a separate, typically much larger regional quota than pd-balanced/pd-ssd, which share the SSD_TOTAL_GB quota -- a real, documented capacity constraint hit during this project's own live testing. Use pd-balanced or pd-ssd only if the target project has confirmed headroom in that quota."
  type        = string
  default     = "$node_disk_type"

  validation {
    condition     = contains(["pd-standard", "pd-balanced", "pd-ssd"], var.node_disk_type)
    error_message = "node_disk_type must be one of: pd-standard, pd-balanced, pd-ssd."
  }
}

variable "node_min_count" {
  description = "Minimum Standard nodes per zone."
  type        = number
  default     = $node_min_count
}

variable "node_max_count" {
  description = "Maximum Standard nodes per zone."
  type        = number
  default     = $node_max_count
}

variable "node_spot" {
  description = "Use Spot VMs for Standard nodes."
  type        = bool
  default     = false
}

variable "create_artifact_registry" {
  description = "Create a regional Docker repository."
  type        = bool
  default     = true
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry repository ID."
  type        = string
  default     = "$artifact_registry_repository_id"
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

CLUSTER_TEMPLATE = """
locals {
  is_standard  = var.cluster_mode == "STANDARD"
  is_autopilot = var.cluster_mode == "AUTOPILOT"

  workload_pool = "$${var.project_id}.svc.id.goog"

  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }
}

resource "google_container_cluster" "standard" {
  count = local.is_standard ? 1 : 0

  name     = var.cluster_name
  project  = var.project_id
  location = var.region

  network    = var.network
  subnetwork = var.subnetwork

  remove_default_node_pool = true
  initial_node_count       = 1
  networking_mode          = "VPC_NATIVE"

  # Even with remove_default_node_pool = true, GKE still briefly
  # creates a transient initial node pool using this cluster-level
  # node_config before Terraform deletes it and creates the real
  # "primary" node pool separately below. Without this block, that
  # transient pool falls back to GKE's raw API default (pd-balanced),
  # which can hit the same SSD_TOTAL_GB quota wall the real node pool
  # is deliberately configured to avoid -- confirmed by hitting exactly
  # this during real live testing.
  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = var.node_disk_size_gb
    disk_type    = var.node_disk_type
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_secondary_range_name
    services_secondary_range_name = var.services_secondary_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = var.master_ipv4_cidr_block
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  release_channel {
    channel = var.release_channel
  }

  workload_identity_config {
    workload_pool = local.workload_pool
  }

  gateway_api_config {
    channel = var.gateway_api_channel
  }

  monitoring_config {
    managed_prometheus {
      enabled = true
    }
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER"]
  }

  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  binary_authorization {
    evaluation_mode = (
      var.enable_binary_authorization
      ? "PROJECT_SINGLETON_POLICY_ENFORCE"
      : "DISABLED"
    )
  }

  enable_shielded_nodes = true
  deletion_protection   = var.deletion_protection
  resource_labels       = local.common_labels
}

resource "google_container_cluster" "autopilot" {
  count = local.is_autopilot ? 1 : 0

  name             = var.cluster_name
  project          = var.project_id
  location         = var.region
  enable_autopilot = true

  network    = var.network
  subnetwork = var.subnetwork

  networking_mode = "VPC_NATIVE"

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_secondary_range_name
    services_secondary_range_name = var.services_secondary_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = var.enable_private_endpoint
    master_ipv4_cidr_block  = var.master_ipv4_cidr_block
  }

  master_authorized_networks_config {
    dynamic "cidr_blocks" {
      for_each = var.master_authorized_networks
      content {
        cidr_block   = cidr_blocks.value.cidr_block
        display_name = cidr_blocks.value.display_name
      }
    }
  }

  release_channel {
    channel = var.release_channel
  }

  workload_identity_config {
    workload_pool = local.workload_pool
  }

  gateway_api_config {
    channel = var.gateway_api_channel
  }

  monitoring_config {
    managed_prometheus {
      enabled = true
    }
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER"]
  }

  binary_authorization {
    evaluation_mode = (
      var.enable_binary_authorization
      ? "PROJECT_SINGLETON_POLICY_ENFORCE"
      : "DISABLED"
    )
  }

  deletion_protection = var.deletion_protection
  resource_labels     = local.common_labels
}
"""

NODE_POOL_TEMPLATE = """
resource "google_container_node_pool" "primary" {
  count = local.is_standard ? 1 : 0

  name     = "$${var.cluster_name}-primary"
  project  = var.project_id
  location = var.region
  cluster  = google_container_cluster.standard[0].name

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.node_machine_type
    disk_size_gb    = var.node_disk_size_gb
    disk_type       = var.node_disk_type
    spot            = var.node_spot
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = local.common_labels

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  depends_on = [google_project_iam_member.node_roles]
}
"""

IAM_TEMPLATE = """
resource "google_service_account" "nodes" {
  project      = var.project_id
  account_id   = substr("$${var.cluster_name}-nodes", 0, 30)
  display_name = "$${var.cluster_name} GKE node service account"
}

locals {
  node_roles = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
    "roles/artifactregistry.reader"
  ])
}

resource "google_project_iam_member" "node_roles" {
  for_each = local.is_standard ? local.node_roles : toset([])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:$${google_service_account.nodes.email}"
}
"""

ARTIFACT_REGISTRY_TEMPLATE = """
resource "google_artifact_registry_repository" "images" {
  count = var.create_artifact_registry ? 1 : 0

  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_repository_id
  description   = "Docker images for $${var.cluster_name}"
  format        = "DOCKER"
  labels        = local.common_labels
}
"""

OUTPUTS_TEMPLATE = """
output "cluster_name" {
  value       = var.cluster_name
  description = "GKE cluster name."
}

output "cluster_mode" {
  value       = var.cluster_mode
  description = "Selected GKE mode."
}

output "workload_identity_pool" {
  value       = local.workload_pool
  description = "Workload Identity Federation pool."
}

output "node_service_account_email" {
  value       = local.is_standard ? google_service_account.nodes.email : null
  description = "Standard node service account."
}

output "artifact_registry_repository" {
  value = (
    var.create_artifact_registry
    ? google_artifact_registry_repository.images[0].name
    : null
  )
  description = "Artifact Registry repository."
}
"""

TFVARS_TEMPLATE = """
project_id   = "your-project-id"
region       = "$region"
cluster_name = "$cluster_name"
cluster_mode = "$cluster_mode"

network    = "projects/your-project/global/networks/your-vpc"
subnetwork = "projects/your-project/regions/$region/subnetworks/your-subnet"

pods_secondary_range_name     = "gke-pods"
services_secondary_range_name = "gke-services"

master_ipv4_cidr_block  = "$master_ipv4_cidr_block"
enable_private_endpoint = $enable_private_endpoint

# master_authorized_networks defaults to allowing all of 10.0.0.0/8.
# Narrow this to your actual management network for production use:
# master_authorized_networks = [
#   { cidr_block = "10.10.0.0/20", display_name = "bastion-subnet" }
# ]

release_channel             = "$release_channel"
gateway_api_channel         = "$gateway_api_channel"
enable_binary_authorization = $enable_binary_authorization
deletion_protection         = $deletion_protection

node_machine_type = "$node_machine_type"
node_disk_size_gb = $node_disk_size_gb
node_disk_type    = "$node_disk_type"
node_min_count    = $node_min_count
node_max_count    = $node_max_count
node_spot         = false

create_artifact_registry        = true
artifact_registry_repository_id = "$artifact_registry_repository_id"

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# Enterprise GKE Platform

This project generates a regional VPC-native GKE cluster in either Standard
or Autopilot mode.

## Security defaults

- Private nodes
- Private control-plane endpoint by default
- Workload Identity Federation for GKE
- Shielded Standard nodes
- Dedicated Standard node service account
- Legacy metadata endpoints disabled
- Binary Authorization support
- Deletion protection enabled
- No service account keys

## Platform capabilities

- Standard or Autopilot
- Regional cluster
- Release channel
- Managed Service for Prometheus
- Workload and system logging
- Gateway API channel
- Standard node-pool autoscaling
- Artifact Registry Docker repository

## Existing infrastructure

The project expects an existing VPC, subnet, Pod secondary range, and Service
secondary range.

## Local validation

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

"""Terraform templates for the Network plugin."""

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
  description = "Region for the subnet and the serverless VPC connector."
  type        = string
  default     = "$region"
}

variable "network_name" {
  description = "Custom-mode VPC network name."
  type        = string
  default     = "$network_name"
}

variable "subnet_name" {
  description = "Regional subnet name."
  type        = string
  default     = "$subnet_name"
}

variable "subnet_cidr" {
  description = "Primary IPv4 CIDR range for the subnet."
  type        = string
  default     = "$subnet_cidr"
}

variable "secondary_ip_ranges" {
  description = "Optional secondary IP ranges keyed by range name."
  type        = map(string)
  $secondary_ip_ranges_default_line
}

variable "private_service_access_range_name" {
  description = "Reserved global address name used for Private Service Access."
  type        = string
  default     = "$private_service_access_range_name"
}

variable "private_service_access_prefix_length" {
  description = "Prefix length of the reserved Private Service Access range."
  type        = number
  default     = $private_service_access_prefix_length
}

variable "enable_serverless_vpc_connector" {
  description = "Create a Serverless VPC Access connector for Cloud Run egress."
  type        = bool
  default     = $enable_serverless_vpc_connector
}

variable "vpc_connector_name" {
  description = "Serverless VPC Access connector name, 1-25 characters."
  type        = string
  default     = "$vpc_connector_name"
}

variable "vpc_connector_cidr" {
  description = "A /28 CIDR range dedicated to the Serverless VPC Access connector."
  type        = string
  default     = "$vpc_connector_cidr"
}

variable "vpc_connector_min_instances" {
  description = "Minimum connector instances."
  type        = number
  default     = $vpc_connector_min_instances
}

variable "vpc_connector_max_instances" {
  description = "Maximum connector instances."
  type        = number
  default     = $vpc_connector_max_instances
}

variable "vpc_connector_machine_type" {
  description = "Machine type backing the connector instances."
  type        = string
  default     = "$vpc_connector_machine_type"
}
"""

NETWORK_TEMPLATE = """
resource "google_compute_network" "this" {
  project                 = var.project_id
  name                     = var.network_name
  auto_create_subnetworks  = false
  routing_mode             = "REGIONAL"
}

resource "google_compute_subnetwork" "this" {
  project                  = var.project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  dynamic "secondary_ip_range" {
    for_each = var.secondary_ip_ranges

    content {
      range_name    = secondary_ip_range.key
      ip_cidr_range = secondary_ip_range.value
    }
  }

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}
"""

PRIVATE_SERVICE_ACCESS_TEMPLATE = """
resource "google_compute_global_address" "private_service_range" {
  project       = var.project_id
  name          = var.private_service_access_range_name
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.private_service_access_prefix_length
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "private_service_access" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]
}
"""

VPC_CONNECTOR_TEMPLATE = """
resource "google_vpc_access_connector" "serverless" {
  count = var.enable_serverless_vpc_connector ? 1 : 0

  project       = var.project_id
  name          = var.vpc_connector_name
  region        = var.region
  network       = google_compute_network.this.name
  ip_cidr_range = var.vpc_connector_cidr
  min_instances = var.vpc_connector_min_instances
  max_instances = var.vpc_connector_max_instances
  machine_type  = var.vpc_connector_machine_type

  lifecycle {
    precondition {
      condition     = var.vpc_connector_max_instances > var.vpc_connector_min_instances
      error_message = "vpc_connector_max_instances must be greater than vpc_connector_min_instances."
    }
  }
}
"""

OUTPUTS_TEMPLATE = """
output "network_id" {
  value = google_compute_network.this.id
}

output "network_name" {
  value = google_compute_network.this.name
}

output "network_self_link" {
  value = google_compute_network.this.self_link
}

output "subnet_id" {
  value = google_compute_subnetwork.this.id
}

output "subnet_name" {
  value = google_compute_subnetwork.this.name
}

output "subnet_self_link" {
  value = google_compute_subnetwork.this.self_link
}

output "private_service_access_connection" {
  value = google_service_networking_connection.private_service_access.id
}

output "vpc_connector_id" {
  value = one(google_vpc_access_connector.serverless[*].id)
}

output "vpc_connector_name" {
  value = one(google_vpc_access_connector.serverless[*].name)
}
"""

TFVARS_TEMPLATE = """
project_id   = "your-project-id"
region       = "$region"
network_name = "$network_name"
subnet_name  = "$subnet_name"
subnet_cidr  = "$subnet_cidr"

secondary_ip_ranges = $secondary_ip_ranges

private_service_access_range_name    = "$private_service_access_range_name"
private_service_access_prefix_length = $private_service_access_prefix_length

enable_serverless_vpc_connector = $enable_serverless_vpc_connector
vpc_connector_name              = "$vpc_connector_name"
vpc_connector_cidr              = "$vpc_connector_cidr"
vpc_connector_min_instances     = $vpc_connector_min_instances
vpc_connector_max_instances     = $vpc_connector_max_instances
vpc_connector_machine_type      = "$vpc_connector_machine_type"
"""

README_TEMPLATE = """
# Networking Foundation

Creates the shared private-networking foundation required by internal
Cloud Run, GKE, and Cloud SQL workloads:

- A custom-mode VPC network
- A regional subnet with Private Google Access and VPC flow logs enabled
- Optional secondary IP ranges, for example GKE pod and service ranges
- A reserved global address and Private Service Access connection, required
  before a private Cloud SQL instance can be attached to this network
- An optional Serverless VPC Access connector for Cloud Run egress

## Security defaults

- `auto_create_subnetworks = false`, subnets are explicit and reviewed
- `private_ip_google_access = true` on the subnet
- VPC flow logs enabled with full metadata
- No public IP ranges or NAT are created by this module

Set `enable_serverless_vpc_connector = false` if the consuming workloads do
not require Cloud Run egress through this VPC.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

"""Root templates for the Project Assembler's GKE + Network + IAM
(Workload Identity) platform recipe.

Unlike the other two assembler recipes, the network here is hand-written
directly at the root level rather than composed from the standalone
Network generator plugin: that generator unconditionally creates Private
Service Access and a Serverless VPC Access connector (a real, ~9-minute
cost in live testing), neither of which GKE needs. This reuses the exact
network + firewall pattern already proven correct while building the
standalone GKE live E2E test earlier -- a plain VPC-native custom-mode
network, a regional subnet with the two secondary IP ranges GKE
requires, and the two firewall rules GKE's private control plane needs
(which a custom-mode VPC does not get automatically, unlike the
`default` network).

GKE and IAM ARE composed from their real generator plugins as
`modules/gke` and `modules/iam`. The IAM module here is deliberately
scoped differently from GKE's own node service account: GKE already
creates and manages its own node-level service account with
infrastructure roles. This IAM module instead creates a dedicated
service account for application *workloads* running as pods, bound via
GKE Workload Identity Federation (`impersonation_role =
"roles/iam.workloadIdentityUser"`) so a specific Kubernetes
ServiceAccount can impersonate it to call GCP APIs -- a distinct,
real-world need this architecture didn't cover before extending the IAM
generator with a configurable `impersonation_role`.
"""

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

VARIABLES_TEMPLATE = """
variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Region applied to every module in this architecture."
  type        = string
  default     = "$region"
}

variable "environment" {
  description = "Environment label applied across every module."
  type        = string
  default     = "$environment"
}

variable "owner" {
  description = "Owner label applied across every module."
  type        = string
  default     = "$owner"
}

variable "application" {
  description = "Application label applied across every module."
  type        = string
  default     = "$application"
}

variable "network_name" {
  description = "Custom-mode VPC network name for the GKE cluster."
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

variable "pods_cidr" {
  description = "Secondary IPv4 CIDR range for GKE pods."
  type        = string
  default     = "$pods_cidr"
}

variable "services_cidr" {
  description = "Secondary IPv4 CIDR range for GKE services."
  type        = string
  default     = "$services_cidr"
}

variable "master_ipv4_cidr_block" {
  description = "Private control-plane CIDR for the GKE cluster."
  type        = string
  default     = "$master_ipv4_cidr_block"
}

variable "cluster_name" {
  description = "GKE cluster name."
  type        = string
  default     = "$cluster_name"
}

variable "node_machine_type" {
  description = "GKE node machine type."
  type        = string
  default     = "$node_machine_type"
}

variable "node_min_count" {
  description = "Minimum nodes per zone."
  type        = number
  default     = $node_min_count
}

variable "node_max_count" {
  description = "Maximum nodes per zone."
  type        = number
  default     = $node_max_count
}

variable "workload_service_account_id" {
  description = "Service account ID for the Workload Identity-bound application service account."
  type        = string
  default     = "$workload_service_account_id"
}

variable "workload_project_roles" {
  description = "Project roles granted to the workload service account."
  type        = list(string)
  $workload_project_roles_default_line
}

variable "k8s_namespace" {
  description = "Kubernetes namespace of the workload's ServiceAccount."
  type        = string
  default     = "$k8s_namespace"
}

variable "k8s_service_account" {
  description = "Kubernetes ServiceAccount name allowed to impersonate the workload service account via Workload Identity."
  type        = string
  default     = "$k8s_service_account"
}
"""

MAIN_TEMPLATE = """
provider "google" {
  project = var.project_id
  region  = var.region
}

# Hand-written network, not a composed generator module -- see the
# module docstring in pipeline_assembler_templates.py's sibling file for
# why: the standalone Network generator unconditionally creates Private
# Service Access and a Serverless VPC Access connector, which GKE does
# not need.

resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "this" {
  project                  = var.project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = var.services_cidr
  }
}

# GKE private clusters require these two rules on any custom-mode VPC --
# confirmed necessary the hard way while building the standalone GKE
# live E2E test. The `default` network has equivalent rules built in;
# custom-mode networks like this one do not.

resource "google_compute_firewall" "allow_internal" {
  project   = var.project_id
  name      = "$${var.network_name}-allow-internal"
  network   = google_compute_network.this.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = [
    var.subnet_cidr,
    var.pods_cidr,
    var.services_cidr,
  ]
}

resource "google_compute_firewall" "allow_master_webhooks" {
  project   = var.project_id
  name      = "$${var.network_name}-allow-master"
  network   = google_compute_network.this.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443", "8443", "9443", "10250", "15017"]
  }

  source_ranges = [var.master_ipv4_cidr_block]
}

module "gke" {
  source = "./modules/gke"

  project_id             = var.project_id
  region                 = var.region
  cluster_name            = var.cluster_name
  network                 = google_compute_network.this.name
  subnetwork               = google_compute_subnetwork.this.name
  pods_secondary_range_name    = "gke-pods"
  services_secondary_range_name = "gke-services"
  master_ipv4_cidr_block   = var.master_ipv4_cidr_block
  node_machine_type        = var.node_machine_type
  node_min_count           = var.node_min_count
  node_max_count           = var.node_max_count

  environment = var.environment
  owner       = var.owner
  application = var.application

  depends_on = [
    google_compute_subnetwork.this,
    google_compute_firewall.allow_internal,
    google_compute_firewall.allow_master_webhooks,
  ]
}

module "iam_workload" {
  source = "./modules/iam"

  project_id            = var.project_id
  region                = var.region
  service_account_id    = var.workload_service_account_id
  project_roles         = var.workload_project_roles
  impersonation_role    = "roles/iam.workloadIdentityUser"
  impersonators = [
    "serviceAccount:$${var.project_id}.svc.id.goog[$${var.k8s_namespace}/$${var.k8s_service_account}]"
  ]

  environment = var.environment
  owner       = var.owner
  application = var.application

  depends_on = [module.gke]
}
"""

OUTPUTS_TEMPLATE = """
output "network_id" {
  value = google_compute_network.this.id
}

output "subnet_id" {
  value = google_compute_subnetwork.this.id
}

output "cluster_name" {
  value = module.gke.cluster_name
}

output "cluster_mode" {
  value = module.gke.cluster_mode
}

output "gke_workload_identity_pool" {
  value = module.gke.workload_identity_pool
}

output "node_service_account_email" {
  value = module.gke.node_service_account_email
}

output "workload_service_account_email" {
  value = module.iam_workload.service_account_email
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

environment = "$environment"
owner       = "$owner"
application = "$application"

network_name = "$network_name"
subnet_name  = "$subnet_name"
subnet_cidr  = "$subnet_cidr"
pods_cidr    = "$pods_cidr"
services_cidr = "$services_cidr"

master_ipv4_cidr_block = "$master_ipv4_cidr_block"

cluster_name       = "$cluster_name"
node_machine_type  = "$node_machine_type"
node_min_count     = $node_min_count
node_max_count     = $node_max_count

workload_service_account_id = "$workload_service_account_id"
workload_project_roles      = $workload_project_roles
k8s_namespace                = "$k8s_namespace"
k8s_service_account          = "$k8s_service_account"
"""

README_TEMPLATE = """
# GKE + Network + IAM (Workload Identity) Platform

Assembled by the Project Assembler. Unlike the other two recipes, the
network here is hand-written directly at the root level (see
`main.tf`), not composed from the standalone Network generator: that
generator unconditionally creates Private Service Access and a
Serverless VPC Access connector, neither of which GKE needs. GKE and IAM
are composed as real generator modules under `modules/`:

- Root `main.tf` — a custom-mode VPC, a regional subnet with the two
  secondary IP ranges GKE requires, and the two firewall rules GKE's
  private control plane needs (a custom-mode VPC gets no firewall rules
  automatically, unlike the `default` network)
- `modules/gke` — a private, VPC-native GKE Standard cluster with its
  own dedicated node service account and least-privilege node IAM roles
- `modules/iam` — a **separate, dedicated service account for
  application workloads** (distinct from GKE's own node service
  account), bound via Workload Identity Federation
  (`impersonation_role = "roles/iam.workloadIdentityUser"`) so the
  Kubernetes ServiceAccount named by `k8s_service_account` in namespace
  `k8s_namespace` can impersonate it to call GCP APIs from pods

After `terraform apply`, annotate your Kubernetes ServiceAccount to
complete the Workload Identity binding:

    kubectl annotate serviceaccount $k8s_service_account \\
      --namespace $k8s_namespace \\
      iam.gke.io/gcp-service-account=$workload_service_account_id@your-project-id.iam.gserviceaccount.com

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

"""Root templates for the Project Assembler's private Cloud Run + Cloud SQL recipe."""

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
  description = "Custom-mode VPC network name shared by every module."
  type        = string
  default     = "$network_name"
}

variable "subnet_cidr" {
  description = "Primary IPv4 CIDR range for the shared application subnet."
  type        = string
  default     = "$subnet_cidr"
}

variable "database_version" {
  description = "Cloud SQL database version."
  type        = string
  default     = "$database_version"
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "$db_tier"
}

variable "db_availability_type" {
  description = "Cloud SQL availability type, ZONAL or REGIONAL."
  type        = string
  default     = "$db_availability_type"
}

variable "database_secret_id" {
  description = "Secret Manager secret ID holding the database credential. No value is stored by Terraform."
  type        = string
  default     = "$database_secret_id"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "$service_name"
}

variable "container_image" {
  description = "Artifact Registry container image URL for Cloud Run."
  type        = string
  default     = "$container_image"
}

variable "container_port" {
  description = "Cloud Run container listening port."
  type        = number
  default     = $container_port
}

variable "allow_unauthenticated" {
  description = "Grant roles/run.invoker to allUsers on the Cloud Run service."
  type        = bool
  default     = $allow_unauthenticated
}
"""

MAIN_TEMPLATE = """
provider "google" {
  project = var.project_id
  region  = var.region
}

module "network" {
  source = "./modules/network"

  project_id   = var.project_id
  region       = var.region
  network_name = var.network_name
  subnet_name  = "$${var.network_name}-subnet"
  subnet_cidr  = var.subnet_cidr
}

module "cloud_sql" {
  source = "./modules/cloud-sql"

  project_id        = var.project_id
  region            = var.region
  instance_name     = "$${var.service_name}-db"
  database_version  = var.database_version
  tier              = var.db_tier
  availability_type = var.db_availability_type
  private_network   = module.network.network_self_link
  environment       = var.environment
  owner             = var.owner
  application       = var.application

  depends_on = [module.network]
}

module "secret_manager" {
  source = "./modules/secret-manager"

  project_id  = var.project_id
  region      = var.region
  secret_ids  = [var.database_secret_id]
  environment = var.environment
  owner       = var.owner
  application = var.application
}

module "cloud_run" {
  source = "./modules/cloud-run"

  project_id            = var.project_id
  region                = var.region
  service_name          = var.service_name
  container_image       = var.container_image
  container_port        = var.container_port
  allow_unauthenticated = var.allow_unauthenticated
  vpc_connector         = module.network.vpc_connector_id
  cloud_sql_instances   = [module.cloud_sql.connection_name]

  secret_environment_variables = {
    DB_PASSWORD = {
      secret  = var.database_secret_id
      version = "latest"
    }
  }

  environment = var.environment
  owner       = var.owner
  application = var.application

  depends_on = [module.network, module.cloud_sql, module.secret_manager]
}
"""

OUTPUTS_TEMPLATE = """
output "cloud_run_service_uri" {
  value = module.cloud_run.service_uri
}

output "cloud_run_runtime_service_account_email" {
  value = module.cloud_run.runtime_service_account_email
}

output "cloud_sql_connection_name" {
  value = module.cloud_sql.connection_name
}

output "cloud_sql_private_ip_address" {
  value     = module.cloud_sql.private_ip_address
  sensitive = true
}

output "network_id" {
  value = module.network.network_id
}

output "vpc_connector_id" {
  value = module.network.vpc_connector_id
}

output "database_secret_id" {
  value = var.database_secret_id
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

environment = "$environment"
owner       = "$owner"
application = "$application"

network_name = "$network_name"
subnet_cidr  = "$subnet_cidr"

database_version    = "$database_version"
db_tier              = "$db_tier"
db_availability_type = "$db_availability_type"
database_secret_id   = "$database_secret_id"

service_name          = "$service_name"
container_image       = "$container_image"
container_port        = $container_port
allow_unauthenticated = $allow_unauthenticated
"""

README_TEMPLATE = """
# Private Cloud Run + Cloud SQL Platform

Assembled by the Project Assembler from four generator plugins, composed
as local Terraform modules under `modules/`:

- `modules/network` — custom-mode VPC, regional subnet, Private Service
  Access, and a Serverless VPC Access connector
- `modules/cloud-sql` — a private PostgreSQL or MySQL instance attached
  to the shared VPC through Private Service Access
- `modules/secret-manager` — a Secret Manager container for the database
  credential, with no secret material generated or stored
- `modules/cloud-run` — a private Cloud Run v2 service with its own
  dedicated runtime service account, routed through the Serverless VPC
  Access connector, with a Cloud SQL Auth Proxy volume mount and a
  Secret Manager environment variable reference

Wiring between modules:

- `cloud_sql.private_network` is set to `module.network.network_self_link`
- `cloud_run.vpc_connector` is set to `module.network.vpc_connector_id`
- `cloud_run.cloud_sql_instances` is set to
  `[module.cloud_sql.connection_name]`
- `cloud_run` reads `DB_PASSWORD` from the `database_secret_id` secret,
  which `secret_manager` also creates using the same variable

After `terraform apply`, populate the database credential out-of-band,
for example:

    gcloud secrets versions add $database_secret_id --data-file=-

Nothing is deployed by this generator. Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

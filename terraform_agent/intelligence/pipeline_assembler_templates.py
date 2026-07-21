"""Root templates for the Project Assembler's BigQuery + Pub/Sub +
Cloud Functions event-driven pipeline recipe."""

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

variable "topic_name" {
  description = "Pub/Sub topic that publishes pipeline events."
  type        = string
  default     = "$topic_name"
}

variable "dataset_id" {
  description = "BigQuery dataset the pipeline function writes into."
  type        = string
  default     = "$dataset_id"
}

variable "deletion_protection" {
  description = "Protect the BigQuery table from accidental deletion. Defaults to true (safe for real deployments); override to false for throwaway test/dev workspaces that need to be destroyed."
  type        = bool
  default     = $deletion_protection
}

variable "table_id" {
  description = "BigQuery table the pipeline function writes into. Passed to the function as an environment variable only; the table itself is created by the bigquery module using its own default schema."
  type        = string
  default     = "$table_id"
}

variable "function_name" {
  description = "Cloud Function name."
  type        = string
  default     = "$function_name"
}

variable "source_bucket_name" {
  description = "Globally unique bucket name for the function source archive."
  type        = string
  default     = "$source_bucket_name"
}

variable "source_archive_path" {
  description = "Local path to a zipped Cloud Function source archive that reads the incoming Pub/Sub message and writes a row to BigQuery. Required with no default so a placeholder path is never evaluated during offline validation."
  type        = string
}

variable "runtime" {
  description = "Cloud Functions runtime identifier, for example python312."
  type        = string
  default     = "$runtime"
}

variable "entry_point" {
  description = "Exported function name invoked in the source code."
  type        = string
  default     = "$entry_point"
}
"""

MAIN_TEMPLATE = """
provider "google" {
  project = var.project_id
  region  = var.region
}

module "pubsub" {
  source = "./modules/pubsub"

  project_id = var.project_id
  region     = var.region
  topics     = [var.topic_name]

  environment = var.environment
  owner       = var.owner
  application = var.application
}

module "cloud_functions" {
  source = "./modules/cloud-functions"

  project_id          = var.project_id
  region              = var.region
  function_name       = var.function_name
  source_bucket_name  = var.source_bucket_name
  source_archive_path = var.source_archive_path
  runtime             = var.runtime
  entry_point         = var.entry_point

  trigger_type         = "PUBSUB"
  pubsub_trigger_topic = module.pubsub.topic_ids[var.topic_name]

  environment_variables = {
    BIGQUERY_DATASET = var.dataset_id
    BIGQUERY_TABLE   = var.table_id
  }

  environment = var.environment
  owner       = var.owner
  application = var.application

  depends_on = [module.pubsub]
}

module "bigquery" {
  source = "./modules/bigquery"

  project_id           = var.project_id
  region               = var.region
  dataset_id           = var.dataset_id
  deletion_protection  = var.deletion_protection

  editor_members = [
    "serviceAccount:$${module.cloud_functions.runtime_service_account_email}"
  ]

  environment = var.environment
  owner       = var.owner
  application = var.application

  depends_on = [module.cloud_functions]
}
"""

OUTPUTS_TEMPLATE = """
output "topic_ids" {
  value = module.pubsub.topic_ids
}

output "cloud_function_name" {
  value = module.cloud_functions.function_name
}

output "cloud_function_runtime_service_account_email" {
  value = module.cloud_functions.runtime_service_account_email
}

output "bigquery_dataset_id" {
  value = module.bigquery.dataset_id
}

output "bigquery_table_ids" {
  value = module.bigquery.table_ids
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

environment = "$environment"
owner       = "$owner"
application = "$application"

topic_name = "$topic_name"
dataset_id = "$dataset_id"
table_id   = "$table_id"
deletion_protection = $deletion_protection

function_name       = "$function_name"
source_bucket_name  = "$source_bucket_name"
source_archive_path = "./dist/function-source.zip"

runtime     = "$runtime"
entry_point = "$entry_point"
"""

README_TEMPLATE = """
# BigQuery + Pub/Sub + Cloud Functions Event Pipeline

Assembled by the Project Assembler from three generator plugins, composed
as local Terraform modules under `modules/`:

- `modules/pubsub` — the topic that receives pipeline events. No
  subscription is generated here: Cloud Functions' native Pub/Sub
  `event_trigger` manages its own underlying Eventarc trigger and
  subscription automatically.
- `modules/cloud-functions` — a Pub/Sub-triggered Cloud Function
  (`trigger_type = "PUBSUB"`), its own dedicated source archive bucket,
  and its own dedicated runtime service account. The function is granted
  `roles/eventarc.eventReceiver` and `roles/run.invoker` on itself, and
  Pub/Sub's own Google-managed service agent is granted
  `roles/iam.serviceAccountTokenCreator` on the function's runtime service
  account -- required for Pub/Sub to invoke the function at all.
- `modules/bigquery` — the dataset the function writes into. The
  function's runtime service account is granted `roles/bigquery.dataEditor`
  on this dataset via `editor_members`, wired directly to
  `module.cloud_functions.runtime_service_account_email`.

Wiring between modules:

- `cloud_functions.pubsub_trigger_topic` is set to
  `module.pubsub.topic_ids[var.topic_name]`
- `bigquery.editor_members` includes
  `serviceAccount:${module.cloud_functions.runtime_service_account_email}`
- The dataset/table names are also passed to the function as
  `BIGQUERY_DATASET`/`BIGQUERY_TABLE` environment variables, for the
  function's own code to use

**This generator does not write your function's application code.** You
still need to write and zip a function that reads the incoming Pub/Sub
message (available via the CloudEvent payload in the
`event_trigger`-invoked function signature) and inserts a row into the
BigQuery table referenced by the `BIGQUERY_DATASET`/`BIGQUERY_TABLE`
environment variables, then point `source_archive_path` at that zip
before running Terraform.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

"""Terraform templates for the Pub/Sub plugin."""

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

variable "topics" {
  description = "Pub/Sub topic names to create."
  type        = list(string)
  $topics_default_line
}

variable "subscriptions" {
  description = "Pub/Sub subscriptions keyed by subscription name."
  type = map(object({
    topic                      = string
    ack_deadline_seconds       = number
    message_retention_duration = string
    enable_dead_letter         = bool
    max_delivery_attempts      = number
  }))
  default = $subscriptions
}

variable "publisher_members" {
  description = "IAM members granted roles/pubsub.publisher on every topic."
  type        = list(string)
  $publisher_members_default_line
}

variable "subscriber_members" {
  description = "IAM members granted roles/pubsub.subscriber on every subscription."
  type        = list(string)
  $subscriber_members_default_line
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
data "google_project" "this" {
  project_id = var.project_id
}

locals {
  common_labels = {
    environment = var.environment
    owner       = var.owner
    application = var.application
    managed_by  = "terraform"
  }

  dead_letter_subscriptions = {
    for name, config in var.subscriptions : name => config
    if config.enable_dead_letter
  }

  pubsub_service_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic" "this" {
  for_each = toset(var.topics)

  project = var.project_id
  name    = each.value
  labels  = local.common_labels
}

resource "google_pubsub_topic" "dead_letter" {
  for_each = local.dead_letter_subscriptions

  project = var.project_id
  name    = "${each.key}-dead-letter"
  labels  = local.common_labels
}
"""

SUBSCRIPTIONS_TEMPLATE = """
resource "google_pubsub_subscription" "this" {
  for_each = var.subscriptions

  project                    = var.project_id
  name                       = each.key
  topic                      = google_pubsub_topic.this[each.value.topic].id
  ack_deadline_seconds       = each.value.ack_deadline_seconds
  message_retention_duration = each.value.message_retention_duration
  labels                     = local.common_labels

  expiration_policy {
    ttl = ""
  }

  dynamic "dead_letter_policy" {
    for_each = each.value.enable_dead_letter ? [1] : []
    content {
      dead_letter_topic     = google_pubsub_topic.dead_letter[each.key].id
      max_delivery_attempts = each.value.max_delivery_attempts
    }
  }

  lifecycle {
    precondition {
      condition     = contains(var.topics, each.value.topic)
      error_message = "Each subscription's topic must be declared in var.topics."
    }
  }
}
"""

IAM_TEMPLATE = """
resource "google_pubsub_topic_iam_member" "publishers" {
  for_each = {
    for pair in flatten([
      for topic in var.topics : [
        for member in var.publisher_members : {
          topic  = topic
          member = member
        }
      ]
    ]) : "${pair.topic}:${pair.member}" => pair
  }

  project = var.project_id
  topic   = google_pubsub_topic.this[each.value.topic].id
  role    = "roles/pubsub.publisher"
  member  = each.value.member
}

resource "google_pubsub_subscription_iam_member" "subscribers" {
  for_each = {
    for pair in flatten([
      for subscription_name in keys(var.subscriptions) : [
        for member in var.subscriber_members : {
          subscription = subscription_name
          member       = member
        }
      ]
    ]) : "${pair.subscription}:${pair.member}" => pair
  }

  project      = var.project_id
  subscription = google_pubsub_subscription.this[each.value.subscription].id
  role         = "roles/pubsub.subscriber"
  member       = each.value.member
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  for_each = local.dead_letter_subscriptions

  project = var.project_id
  topic   = google_pubsub_topic.dead_letter[each.key].id
  role    = "roles/pubsub.publisher"
  member  = local.pubsub_service_agent
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  for_each = local.dead_letter_subscriptions

  project      = var.project_id
  subscription = google_pubsub_subscription.this[each.key].id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_service_agent
}
"""

OUTPUTS_TEMPLATE = """
output "topic_ids" {
  value = { for name, topic in google_pubsub_topic.this : name => topic.id }
}

output "subscription_ids" {
  value = {
    for name, subscription in google_pubsub_subscription.this :
    name => subscription.id
  }
}

output "dead_letter_topic_ids" {
  value = {
    for name, topic in google_pubsub_topic.dead_letter : name => topic.id
  }
}
"""

TFVARS_TEMPLATE = """
project_id = "your-project-id"
region     = "$region"

topics = $topics

subscriptions = $subscriptions

publisher_members  = $publisher_members
subscriber_members = $subscriber_members

environment = "$environment"
owner       = "$owner"
application = "$application"
"""

README_TEMPLATE = """
# Pub/Sub Messaging Foundation

Creates one or more Pub/Sub topics and subscriptions with least-privilege
IAM bindings and optional dead-letter queues.

## Security defaults

- Subscriptions never expire (`expiration_policy.ttl = ""`), preventing
  accidental data loss from inactivity-based deletion.
- Publisher and subscriber access is granted per-topic and
  per-subscription only, never project-wide.
- Dead-letter queues are opt-in per subscription
  (`enable_dead_letter = true`). When enabled, this project also grants
  the required Pub/Sub service agent roles on the dead-letter topic and
  the source subscription, matching Google's documented dead-letter
  configuration requirements.

Each subscription's `topic` must reference a name declared in `topics`;
this is enforced with a plan-time precondition.

Validation:

    terraform fmt -recursive
    terraform init -backend=false
    terraform validate

No plan, apply, destroy, or deployment is performed.
"""

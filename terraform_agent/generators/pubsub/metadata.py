"""Metadata for the Pub/Sub generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

PUBSUB_METADATA = ServiceMetadata(
    service_name="pubsub",
    display_name="Google Cloud Pub/Sub",
    provider="google",
    resources=(
        "google_pubsub_topic.this",
        "google_pubsub_topic.dead_letter",
        "google_pubsub_subscription.this",
        "google_pubsub_topic_iam_member.publishers",
        "google_pubsub_topic_iam_member.dead_letter_publisher",
        "google_pubsub_subscription_iam_member.subscribers",
        "google_pubsub_subscription_iam_member.dead_letter_subscriber",
    ),
    supported_features=(
        "multi_topic_support",
        "durable_subscriptions",
        "dead_letter_queues",
        "least_privilege_publisher_bindings",
        "least_privilege_subscriber_bindings",
        "never_expiring_subscriptions",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "subscriptions.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

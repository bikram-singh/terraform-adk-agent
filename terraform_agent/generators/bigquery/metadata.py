"""Metadata for the BigQuery generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

BIGQUERY_METADATA = ServiceMetadata(
    service_name="bigquery",
    display_name="Google BigQuery",
    provider="google",
    resources=(
        "google_bigquery_dataset.this",
        "google_bigquery_table.this",
        "google_bigquery_dataset_iam_member.readers",
        "google_bigquery_dataset_iam_member.editors",
    ),
    supported_features=(
        "multi_table_support",
        "time_partitioning",
        "cmek_optional",
        "deletion_protection",
        "least_privilege_iam",
        "configurable_table_expiration",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "tables.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

"""Metadata for the GCS generator plugin."""

from terraform_agent.generators.base import ServiceMetadata


GCS_METADATA = ServiceMetadata(
    service_name="gcs",
    display_name="Google Cloud Storage",
    provider="google",
    resources=("google_storage_bucket.this",),
    supported_features=(
        "uniform_bucket_level_access",
        "public_access_prevention",
        "versioning",
        "lifecycle_rules",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

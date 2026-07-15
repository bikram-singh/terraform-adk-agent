"""Metadata for the Cloud Functions generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

CLOUD_FUNCTIONS_METADATA = ServiceMetadata(
    service_name="cloud-functions",
    display_name="Google Cloud Functions (2nd gen)",
    provider="google",
    resources=(
        "google_storage_bucket.source",
        "google_storage_bucket_object.source_archive",
        "google_service_account.runtime",
        "google_cloudfunctions2_function.this",
        "google_project_iam_member.runtime_roles",
        "google_secret_manager_secret_iam_member.secret_access",
        "google_cloudfunctions2_function_iam_member.public_invoker",
    ),
    supported_features=(
        "http_trigger",
        "dedicated_service_account",
        "private_by_default",
        "configurable_ingress",
        "environment_variables",
        "secret_manager_environment_variables",
        "min_max_scaling",
        "cpu_memory_limits",
        "serverless_vpc_access_connector",
        "least_privilege_iam",
        "uniform_bucket_level_access_source_bucket",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

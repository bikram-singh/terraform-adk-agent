"""Metadata for the Cloud Run generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

CLOUD_RUN_METADATA = ServiceMetadata(
    service_name="cloud-run",
    display_name="Google Cloud Run",
    provider="google",
    resources=(
        "google_service_account.runtime",
        "google_cloud_run_v2_service.this",
        "google_cloud_run_v2_service_iam_member.public_invoker",
        "google_project_iam_member.runtime_roles",
        "google_project_iam_member.cloud_sql_client",
        "google_secret_manager_secret_iam_member.secret_access",
    ),
    supported_features=(
        "dedicated_service_account",
        "artifact_registry_image",
        "private_by_default",
        "configurable_ingress",
        "environment_variables",
        "secret_manager_environment_variables",
        "min_max_scaling",
        "cpu_memory_limits",
        "serverless_vpc_access_connector",
        "cloud_sql_volume",
        "least_privilege_iam",
        "deletion_protection",
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

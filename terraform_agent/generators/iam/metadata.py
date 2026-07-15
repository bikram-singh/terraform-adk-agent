"""Metadata for the IAM generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

IAM_METADATA = ServiceMetadata(
    service_name="iam",
    display_name="Google Cloud IAM Foundation",
    provider="google",
    resources=(
        "google_service_account.this",
        "google_project_iam_member.runtime_roles",
        "google_service_account_iam_member.impersonators",
    ),
    supported_features=(
        "dedicated_runtime_identity",
        "least_privilege_project_roles",
        "scoped_impersonation_bindings",
        "rejects_owner_and_editor_roles",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "project_iam.tf",
        "impersonation.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

"""Metadata for the Secret Manager generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

SECRET_MANAGER_METADATA = ServiceMetadata(
    service_name="secret-manager",
    display_name="Google Secret Manager",
    provider="google",
    resources=(
        "google_secret_manager_secret.this",
        "google_secret_manager_secret_iam_member.accessor",
    ),
    supported_features=(
        "multi_secret_support",
        "automatic_or_user_managed_replication",
        "least_privilege_accessor_bindings",
        "no_secret_material_in_terraform",
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

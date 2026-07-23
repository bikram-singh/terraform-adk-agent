"""Metadata for the Artifact Registry generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

ARTIFACT_REGISTRY_METADATA = ServiceMetadata(
    service_name="artifact-registry",
    display_name="Google Artifact Registry",
    provider="google",
    resources=(
        "google_artifact_registry_repository.this",
        "google_artifact_registry_repository_iam_member.readers",
        "google_artifact_registry_repository_iam_member.writers",
    ),
    supported_features=(
        "docker_maven_npm_python_apt_yum_generic_formats",
        "least_privilege_reader_writer_bindings",
        "cleanup_policy_with_safe_dry_run_default",
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

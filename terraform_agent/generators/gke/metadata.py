"""Metadata for the GKE generator plugin."""

from terraform_agent.generators.base import ServiceMetadata


GKE_METADATA = ServiceMetadata(
    service_name="gke",
    display_name="Google Kubernetes Engine",
    provider="google",
    resources=(
        "google_container_cluster.standard",
        "google_container_cluster.autopilot",
        "google_container_node_pool.primary",
        "google_service_account.nodes",
        "google_project_iam_member.node_roles",
        "google_artifact_registry_repository.images",
    ),
    supported_features=(
        "standard_or_autopilot",
        "private_nodes",
        "private_control_plane",
        "workload_identity_federation",
        "release_channel",
        "gateway_api",
        "managed_prometheus",
        "network_policy",
        "shielded_nodes",
        "binary_authorization",
        "node_pool_autoscaling",
        "artifact_registry",
        "least_privilege_node_service_account",
        "deletion_protection",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "cluster.tf",
        "node_pool.tf",
        "iam.tf",
        "artifact_registry.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

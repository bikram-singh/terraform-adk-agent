"""Metadata for the Network generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

NETWORK_METADATA = ServiceMetadata(
    service_name="network",
    display_name="Google Cloud Networking Foundation",
    provider="google",
    resources=(
        "google_compute_network.this",
        "google_compute_subnetwork.this",
        "google_compute_global_address.private_service_range",
        "google_service_networking_connection.private_service_access",
        "google_vpc_access_connector.serverless",
    ),
    supported_features=(
        "custom_mode_vpc",
        "regional_subnet",
        "private_google_access",
        "secondary_ip_ranges",
        "flow_logs",
        "private_service_access",
        "serverless_vpc_connector",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "network.tf",
        "private_service_access.tf",
        "vpc_connector.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

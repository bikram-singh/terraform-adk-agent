"""High-level ADK tools backed by the generator framework."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.engine import (
    generate_intelligent_cloud_run_project,
    generate_intelligent_gcs_project,
    generate_intelligent_gke_project,
)


def generate_gcs_terraform_project(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> dict[str, Any]:
    """Generate and locally validate a secure GCS Terraform project."""

    return generate_intelligent_gcs_project(
        workspace_name=workspace_name,
        region=region,
        environment=environment,
        owner=owner,
        application=application,
        noncurrent_version_retention_days=(
            noncurrent_version_retention_days
        ),
    )


def generate_cloud_run_terraform_project(
    workspace_name: str,
    service_name: str,
    container_image: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    container_port: int = 8080,
    cpu: str = "1",
    memory: str = "512Mi",
    min_instances: int = 0,
    max_instances: int = 5,
    ingress: str = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
    allow_unauthenticated: bool = False,
    deletion_protection: bool = True,
) -> dict[str, Any]:
    """Generate and locally validate a Cloud Run Terraform project."""

    return generate_intelligent_cloud_run_project(
        workspace_name=workspace_name,
        service_name=service_name,
        container_image=container_image,
        region=region,
        environment=environment,
        owner=owner,
        application=application,
        container_port=container_port,
        cpu=cpu,
        memory=memory,
        min_instances=min_instances,
        max_instances=max_instances,
        ingress=ingress,
        allow_unauthenticated=allow_unauthenticated,
        deletion_protection=deletion_protection,
    )


def generate_gke_terraform_project(
    workspace_name: str,
    cluster_name: str,
    network: str,
    subnetwork: str,
    pods_secondary_range_name: str,
    services_secondary_range_name: str,
    region: str = "asia-south1",
    cluster_mode: str = "STANDARD",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    master_ipv4_cidr_block: str = "172.16.0.0/28",
    enable_private_endpoint: bool = True,
    release_channel: str = "REGULAR",
    gateway_api_channel: str = "CHANNEL_STANDARD",
    enable_binary_authorization: bool = True,
    deletion_protection: bool = True,
    node_machine_type: str = "e2-standard-4",
    node_disk_size_gb: int = 100,
    node_min_count: int = 1,
    node_max_count: int = 3,
    artifact_registry_repository_id: str = "gke-images",
) -> dict[str, Any]:
    """
    Generate and locally validate an enterprise GKE Terraform project.

    Supports Standard or Autopilot, private networking, Workload Identity
    Federation, Gateway API, managed monitoring, Artifact Registry, and a
    hardened Standard node pool. Nothing is deployed.
    """

    return generate_intelligent_gke_project(
        workspace_name=workspace_name,
        cluster_name=cluster_name,
        network=network,
        subnetwork=subnetwork,
        pods_secondary_range_name=pods_secondary_range_name,
        services_secondary_range_name=services_secondary_range_name,
        region=region,
        cluster_mode=cluster_mode,
        environment=environment,
        owner=owner,
        application=application,
        master_ipv4_cidr_block=master_ipv4_cidr_block,
        enable_private_endpoint=enable_private_endpoint,
        release_channel=release_channel,
        gateway_api_channel=gateway_api_channel,
        enable_binary_authorization=enable_binary_authorization,
        deletion_protection=deletion_protection,
        node_machine_type=node_machine_type,
        node_disk_size_gb=node_disk_size_gb,
        node_min_count=node_min_count,
        node_max_count=node_max_count,
        artifact_registry_repository_id=(
            artifact_registry_repository_id
        ),
    )

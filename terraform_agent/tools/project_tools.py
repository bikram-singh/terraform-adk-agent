"""High-level ADK tools backed by the generator framework."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.engine import (
    generate_intelligent_cloud_functions_project,
    generate_intelligent_cloud_run_project,
    generate_intelligent_cloud_sql_project,
    generate_intelligent_gcs_project,
    generate_intelligent_gke_project,
    generate_intelligent_iam_project,
    generate_intelligent_network_project,
    generate_intelligent_secret_manager_project,
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
def generate_cloud_sql_terraform_project(
    workspace_name: str,
    instance_name: str,
    private_network: str,
    region: str = "asia-south1",
    database_version: str = "POSTGRES_16",
    tier: str = "db-custom-2-7680",
    availability_type: str = "REGIONAL",
    disk_size_gb: int = 100,
    database_name: str = "application",
    enable_iam_database_authentication: bool = True,
    backup_start_time: str = "02:00",
    backup_retained_count: int = 14,
    transaction_log_retention_days: int = 7,
    maintenance_day: int = 7,
    maintenance_hour: int = 3,
    deletion_protection: bool = True,
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
) -> dict[str, Any]:
    """
    Generate and locally validate a private Cloud SQL project.

    The VPC and Private Service Access connection must already exist.
    No database password is generated and nothing is deployed.
    """

    return generate_intelligent_cloud_sql_project(
        workspace_name=workspace_name,
        instance_name=instance_name,
        private_network=private_network,
        region=region,
        database_version=database_version,
        tier=tier,
        availability_type=availability_type,
        disk_size_gb=disk_size_gb,
        database_name=database_name,
        enable_iam_database_authentication=(
            enable_iam_database_authentication
        ),
        backup_start_time=backup_start_time,
        backup_retained_count=backup_retained_count,
        transaction_log_retention_days=(
            transaction_log_retention_days
        ),
        maintenance_day=maintenance_day,
        maintenance_hour=maintenance_hour,
        deletion_protection=deletion_protection,
        environment=environment,
        owner=owner,
        application=application,
    )


def generate_network_terraform_project(
    workspace_name: str,
    network_name: str,
    region: str = "asia-south1",
    subnet_name: str = "",
    subnet_cidr: str = "10.0.0.0/20",
    secondary_ip_ranges: dict[str, str] | None = None,
    private_service_access_range_name: str = "",
    private_service_access_prefix_length: int = 16,
    enable_serverless_vpc_connector: bool = True,
    vpc_connector_name: str = "",
    vpc_connector_cidr: str = "10.10.0.0/28",
    vpc_connector_min_instances: int = 2,
    vpc_connector_max_instances: int = 3,
    vpc_connector_machine_type: str = "e2-micro",
) -> dict[str, Any]:
    """
    Generate and locally validate a private networking foundation project.

    Creates a custom-mode VPC, a regional subnet with Private Google
    Access, a reserved Private Service Access range and connection, and
    an optional Serverless VPC Access connector. Nothing is deployed.
    """

    return generate_intelligent_network_project(
        workspace_name=workspace_name,
        network_name=network_name,
        region=region,
        subnet_name=subnet_name or f"{network_name}-subnet",
        subnet_cidr=subnet_cidr,
        secondary_ip_ranges=secondary_ip_ranges or {},
        private_service_access_range_name=(
            private_service_access_range_name
            or f"{network_name}-psa-range"
        ),
        private_service_access_prefix_length=(
            private_service_access_prefix_length
        ),
        enable_serverless_vpc_connector=enable_serverless_vpc_connector,
        vpc_connector_name=(
            vpc_connector_name or f"{network_name}-connector"
        ),
        vpc_connector_cidr=vpc_connector_cidr,
        vpc_connector_min_instances=vpc_connector_min_instances,
        vpc_connector_max_instances=vpc_connector_max_instances,
        vpc_connector_machine_type=vpc_connector_machine_type,
    )


def generate_secret_manager_terraform_project(
    workspace_name: str,
    secret_ids: list[str],
    region: str = "asia-south1",
    replication_locations: list[str] | None = None,
    accessor_members: list[str] | None = None,
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
) -> dict[str, Any]:
    """
    Generate and locally validate a Secret Manager project.

    Creates one Secret Manager secret container per entry in secret_ids
    and grants roles/secretmanager.secretAccessor to accessor_members.
    No secret version or secret material is generated or stored.
    """

    return generate_intelligent_secret_manager_project(
        workspace_name=workspace_name,
        secret_ids=secret_ids,
        region=region,
        replication_locations=replication_locations or [],
        accessor_members=accessor_members or [],
        environment=environment,
        owner=owner,
        application=application,
    )


def generate_iam_terraform_project(
    workspace_name: str,
    service_account_id: str,
    project_roles: list[str],
    region: str = "asia-south1",
    service_account_display_name: str = "",
    impersonators: list[str] | None = None,
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
) -> dict[str, Any]:
    """
    Generate and locally validate an IAM foundation project.

    Creates a dedicated runtime service account, grants the requested
    least-privilege project_roles (roles/owner and roles/editor are
    rejected), and optionally grants scoped impersonation access to
    specific impersonators. Nothing is deployed.
    """

    return generate_intelligent_iam_project(
        workspace_name=workspace_name,
        service_account_id=service_account_id,
        project_roles=project_roles,
        region=region,
        service_account_display_name=(
            service_account_display_name
            or f"{service_account_id} runtime identity"
        ),
        impersonators=impersonators or [],
        environment=environment,
        owner=owner,
        application=application,
    )


def generate_cloud_functions_terraform_project(
    workspace_name: str,
    function_name: str,
    source_archive_path: str,
    region: str = "asia-south1",
    source_bucket_name: str = "",
    runtime: str = "python312",
    entry_point: str = "main",
    available_memory: str = "256M",
    available_cpu: str = "1",
    timeout_seconds: int = 60,
    min_instance_count: int = 0,
    max_instance_count: int = 10,
    ingress_settings: str = "ALLOW_INTERNAL_ONLY",
    allow_unauthenticated: bool = False,
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
) -> dict[str, Any]:
    """
    Generate and locally validate a Cloud Functions (2nd gen) project.

    Creates a private-by-default HTTP-triggered Cloud Function, a
    dedicated source archive bucket, and a dedicated runtime service
    account. Only HTTP triggers are supported. No secret material is
    generated. Nothing is deployed.
    """

    return generate_intelligent_cloud_functions_project(
        workspace_name=workspace_name,
        function_name=function_name,
        source_archive_path=source_archive_path,
        region=region,
        source_bucket_name=(
            source_bucket_name or f"{function_name}-source"
        ),
        runtime=runtime,
        entry_point=entry_point,
        available_memory=available_memory,
        available_cpu=available_cpu,
        timeout_seconds=timeout_seconds,
        min_instance_count=min_instance_count,
        max_instance_count=max_instance_count,
        ingress_settings=ingress_settings,
        allow_unauthenticated=allow_unauthenticated,
        environment=environment,
        owner=owner,
        application=application,
    )
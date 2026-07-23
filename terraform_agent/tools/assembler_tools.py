"""High-level ADK tool for the multi-service Project Assembler."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)
from terraform_agent.intelligence.pipeline_assembler import (
    assemble_bigquery_pubsub_pipeline,
)
from terraform_agent.intelligence.gke_platform_assembler import (
    assemble_gke_workload_identity_platform,
)


def assemble_private_cloud_run_postgres_platform(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "app",
    network_name: str = "",
    subnet_cidr: str = "10.0.0.0/20",
    database_version: str = "POSTGRES_16",
    db_tier: str = "db-custom-2-7680",
    db_availability_type: str = "REGIONAL",
    db_deletion_protection: bool = True,
    database_secret_id: str = "database-password",
    service_name: str = "",
    container_image: str = "",
    container_port: int = 8080,
    allow_unauthenticated: bool = False,
) -> dict[str, Any]:
    """
    Assemble a complete private Cloud Run + Cloud SQL platform in one call.

    Invokes the network, Cloud SQL, Secret Manager, and Cloud Run
    generators, composes their output as local Terraform modules inside
    one workspace, wires the required cross-service references (VPC,
    Private Service Access, Serverless VPC Access connector, Cloud SQL
    connection name, and the database secret reference), and runs a
    single local validation pass over the assembled tree.

    Cloud Run creates and manages its own dedicated runtime service
    account and least-privilege IAM bindings, so a separate IAM module is
    not part of this recipe. No database password or secret material is
    generated. Nothing is deployed.
    """

    return assemble_private_cloud_run_cloud_sql_project(
        workspace_name=workspace_name,
        region=region,
        environment=environment,
        owner=owner,
        application=application,
        network_name=network_name,
        subnet_cidr=subnet_cidr,
        database_version=database_version,
        db_tier=db_tier,
        db_availability_type=db_availability_type,
        db_deletion_protection=db_deletion_protection,
        database_secret_id=database_secret_id,
        service_name=service_name,
        container_image=container_image,
        container_port=container_port,
        allow_unauthenticated=allow_unauthenticated,
    )


def assemble_event_driven_data_pipeline(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "pipeline",
    topic_name: str = "",
    dataset_id: str = "",
    table_id: str = "events",
    function_name: str = "",
    source_bucket_name: str = "",
    runtime: str = "python312",
    entry_point: str = "main",
) -> dict[str, Any]:
    """
    Assemble a complete BigQuery + Pub/Sub + Cloud Functions event
    pipeline in one call.

    Invokes the pubsub, cloud-functions, and bigquery generators, composes
    their output as local Terraform modules inside one workspace, and
    wires the required cross-service references: the Cloud Function's
    native Pub/Sub event trigger points at the generated topic, and the
    function's dedicated runtime service account is granted
    `roles/bigquery.dataEditor` on the generated dataset. No push
    subscription is created -- Cloud Functions' event trigger manages its
    own underlying Eventarc trigger and subscription automatically.

    This does not generate your function's application code. Provide a
    zipped function source (via `source_archive_path` in the generated
    tfvars) that reads the incoming Pub/Sub message and writes a row to
    BigQuery before running Terraform. Nothing is deployed.
    """

    return assemble_bigquery_pubsub_pipeline(
        workspace_name=workspace_name,
        region=region,
        environment=environment,
        owner=owner,
        application=application,
        topic_name=topic_name,
        dataset_id=dataset_id,
        table_id=table_id,
        function_name=function_name,
        source_bucket_name=source_bucket_name,
        runtime=runtime,
        entry_point=entry_point,
    )


def assemble_gke_platform(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "platform",
    network_name: str = "",
    subnet_cidr: str = "10.20.0.0/22",
    pods_cidr: str = "10.24.0.0/14",
    services_cidr: str = "10.28.0.0/20",
    master_ipv4_cidr_block: str = "172.16.0.0/28",
    cluster_name: str = "",
    node_machine_type: str = "e2-standard-4",
    node_min_count: int = 1,
    node_max_count: int = 3,
    workload_service_account_id: str = "",
    workload_project_roles: list[str] | None = None,
    k8s_namespace: str = "default",
    k8s_service_account: str = "",
) -> dict[str, Any]:
    """
    Assemble a complete private GKE cluster with a Workload
    Identity-bound application platform in one call.

    Invokes the gke and iam generators, composes their output as local
    Terraform modules inside one workspace, and wires a hand-written
    network + firewall setup around them (not the standalone Network
    generator, which creates Private Service Access and a Serverless VPC
    Access connector that GKE doesn't need). The IAM module's service
    account is distinct from GKE's own node service account: it's meant
    for application workloads running as pods, bound via
    `roles/iam.workloadIdentityUser` so the given Kubernetes
    ServiceAccount can impersonate it to call GCP APIs. Nothing is
    deployed.
    """

    return assemble_gke_workload_identity_platform(
        workspace_name=workspace_name,
        region=region,
        environment=environment,
        owner=owner,
        application=application,
        network_name=network_name,
        subnet_cidr=subnet_cidr,
        pods_cidr=pods_cidr,
        services_cidr=services_cidr,
        master_ipv4_cidr_block=master_ipv4_cidr_block,
        cluster_name=cluster_name,
        node_machine_type=node_machine_type,
        node_min_count=node_min_count,
        node_max_count=node_max_count,
        workload_service_account_id=workload_service_account_id,
        workload_project_roles=workload_project_roles,
        k8s_namespace=k8s_namespace,
        k8s_service_account=k8s_service_account,
    )

"""High-level ADK tool for the multi-service Project Assembler."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)
from terraform_agent.intelligence.pipeline_assembler import (
    assemble_bigquery_pubsub_pipeline,
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

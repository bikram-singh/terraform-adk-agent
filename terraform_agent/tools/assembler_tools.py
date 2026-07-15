"""High-level ADK tool for the multi-service Project Assembler."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
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

"""High-level ADK tool for the Enterprise AI Infrastructure Architect (v1.0)."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.architect import design_infrastructure


def design_infrastructure_platform(
    request: str,
    workspace_name: str,
    region: str = "",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "",
    network_name: str = "",
    subnet_cidr: str = "10.0.0.0/20",
    database_version: str = "",
    db_tier: str = "db-custom-2-7680",
    db_availability_type: str = "REGIONAL",
    database_secret_id: str = "database-password",
    service_name: str = "",
    container_image: str = "",
    container_port: int = 8080,
    allow_unauthenticated: bool = False,
) -> dict[str, Any]:
    """
    Turn one natural-language infrastructure request into a validated
    Terraform project.

    Call this first for any request describing a business need or a
    multi-service architecture, for example "Create a private Cloud Run
    API connected to PostgreSQL" or "Build a secure internal API
    platform on GCP". It detects the architecture, builds the dependency
    graph, and, when the recipe is fully supported, assembles and locally
    validates every required module (network, Cloud SQL, Secret Manager,
    Cloud Run) in this single call.

    Only the private Cloud Run + Cloud SQL recipe is fully supported
    today. Unsupported requests return a structured error listing the
    supported recipes and the individual generators available instead of
    a partial or misleading project. Leave region, database_version, and
    allow_unauthenticated empty/default to infer them from the request
    text; pass explicit values to override inference. Nothing is ever
    deployed.
    """

    return design_infrastructure(
        request=request,
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

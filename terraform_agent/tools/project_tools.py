"""High-level ADK tools backed by the generator framework."""

from __future__ import annotations
from typing import Any
from terraform_agent.intelligence import generate_intelligent_gcs_project
from terraform_agent.intelligence.engine import (
    generate_intelligent_cloud_run_project,
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
        noncurrent_version_retention_days=
            noncurrent_version_retention_days,
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
    """Generate and locally validate a production-ready Cloud Run project."""
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

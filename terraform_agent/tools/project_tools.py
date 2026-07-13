"""High-level ADK tools backed by the Terraform Intelligence Engine."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence import generate_intelligent_gcs_project


def generate_gcs_terraform_project(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> dict[str, Any]:
    """
    Generate and locally validate a complete secure GCS Terraform project.

    This stable ADK tool delegates to the Version 0.4 intelligence pipeline.
    It never deploys infrastructure.
    """

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

"""Service-neutral orchestration pipeline."""

from __future__ import annotations

from typing import Any

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.base.validation import validate_workspace_name
from terraform_agent.intelligence.models import ResourcePlan
from terraform_agent.intelligence.registry import get_generator
from terraform_agent.intelligence.reporting import build_validation_report
from terraform_agent.tools.file_tools import write_generated_file
from terraform_agent.tools.terraform_tools import terraform_full_validation
from terraform_agent.tools.workspace_tools import create_workspace


def generate_service_project(
    service: str,
    workspace_name: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Generate and validate a project through a registered plugin."""

    try:
        workspace = validate_workspace_name(workspace_name)
        generator = get_generator(service)
        generated = generator.generate(
            GeneratorContext(
                workspace_name=workspace,
                values=values,
            )
        )
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "stage": "analysis_or_generation",
            "message": str(exc),
            "deployment_performed": False,
        }

    plan = ResourcePlan(
        service=generated.metadata.service_name,
        workspace_name=workspace,
        resources=generated.metadata.resources,
        generated_files=(
            *generated.metadata.generated_files,
            "validation-report.md",
        ),
        security_controls=generated.metadata.supported_features,
        request=dict(values),
    )

    workspace_result = create_workspace(
        service=plan.service,
        workspace_name=workspace,
    )
    if workspace_result["status"] != "success":
        return {
            "status": "error",
            "stage": "workspace_creation",
            "plan": plan.to_dict(),
            "workspace": workspace_result,
            "deployment_performed": False,
        }

    file_results = []
    for filename, content in generated.files.items():
        result = write_generated_file(
            workspace_name=workspace,
            filename=filename,
            content=content,
            overwrite=False,
        )
        file_results.append(result)
        if result["status"] != "success":
            return {
                "status": "error",
                "stage": "file_generation",
                "plan": plan.to_dict(),
                "workspace": workspace_result,
                "files": file_results,
                "deployment_performed": False,
            }

    validation = terraform_full_validation(workspace)
    report = build_validation_report(plan, validation)
    report_result = write_generated_file(
        workspace_name=workspace,
        filename="validation-report.md",
        content=report,
        overwrite=False,
    )

    return {
        "status": validation["status"],
        "stage": "complete",
        "plan": plan.to_dict(),
        "workspace": workspace_result,
        "files": file_results,
        "validation": validation,
        "validation_report": report_result,
        "deployment_performed": False,
        "message": (
            "Multi-Service Generator Framework completed generation and "
            "local validation. No infrastructure was deployed."
        ),
    }


def generate_intelligent_gcs_project(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> dict[str, Any]:
    """Compatibility wrapper for the existing GCS ADK tool."""

    return generate_service_project(
        service="gcs",
        workspace_name=workspace_name,
        values={
            "region": region,
            "environment": environment,
            "owner": owner,
            "application": application,
            "noncurrent_version_retention_days": (
                noncurrent_version_retention_days
            ),
        },
    )

"""Orchestration pipeline for Terraform intelligence."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.analyzer import analyze_gcs_request
from terraform_agent.intelligence.planner import plan_gcs_project
from terraform_agent.intelligence.registry import get_generator
from terraform_agent.intelligence.reporting import build_validation_report
from terraform_agent.tools.file_tools import write_generated_file
from terraform_agent.tools.terraform_tools import terraform_full_validation
from terraform_agent.tools.workspace_tools import create_workspace


def generate_intelligent_gcs_project(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> dict[str, Any]:
    """
    Analyze, plan, generate, and locally validate a secure GCS project.

    No plan, apply, destroy, import, or state modification is performed.
    """

    try:
        request = analyze_gcs_request(
            workspace_name=workspace_name,
            region=region,
            environment=environment,
            owner=owner,
            application=application,
            noncurrent_version_retention_days=(
                noncurrent_version_retention_days
            ),
        )
        plan = plan_gcs_project(request)
    except ValueError as exc:
        return {
            "status": "error",
            "stage": "analysis",
            "message": str(exc),
            "deployment_performed": False,
        }

    workspace_result = create_workspace(
        service=plan.service,
        workspace_name=plan.workspace_name,
    )
    if workspace_result["status"] != "success":
        return {
            "status": "error",
            "stage": "workspace_creation",
            "plan": plan.to_dict(),
            "workspace": workspace_result,
            "deployment_performed": False,
        }

    generator = get_generator(plan.service)
    generated = generator(
        region=request.region,
        environment=request.environment,
        owner=request.owner,
        application=request.application,
        noncurrent_version_retention_days=(
            request.noncurrent_version_retention_days
        ),
    )

    file_results: list[dict[str, Any]] = []
    for filename, content in generated.files.items():
        result = write_generated_file(
            workspace_name=plan.workspace_name,
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

    validation = terraform_full_validation(plan.workspace_name)
    report = build_validation_report(plan, validation)
    report_result = write_generated_file(
        workspace_name=plan.workspace_name,
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
            "Terraform Intelligence Engine completed analysis, planning, "
            "generation, and local validation. No infrastructure was deployed."
        ),
    }

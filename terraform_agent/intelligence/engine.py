"""Service-neutral orchestration pipeline."""

from __future__ import annotations

from typing import Any

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.base.validation import validate_workspace_name
from terraform_agent.intelligence.models import ResourcePlan
from terraform_agent.intelligence.registry import get_generator
from terraform_agent.intelligence.reporting import build_validation_report
from terraform_agent.tools.file_tools import (
    write_plugin_generated_file,
)
from terraform_agent.tools.terraform_tools import terraform_full_validation
from terraform_agent.tools.workspace_tools import create_workspace


_ENGINE_OWNED_FILES = frozenset({"validation-report.md"})


def _validate_plugin_file_contract(
    generated_files: set[str],
    declared_files: set[str],
) -> None:
    """Ensure a plugin emits exactly the files declared in its metadata."""

    undeclared = generated_files - declared_files
    missing = declared_files - generated_files
    problems: list[str] = []

    if undeclared:
        problems.append(f"undeclared generated files: {sorted(undeclared)}")
    if missing:
        problems.append(f"declared files not generated: {sorted(missing)}")

    if problems:
        raise ValueError(
            "Generator file contract violation: " + "; ".join(problems)
        )


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
            GeneratorContext(workspace_name=workspace, values=values)
        )

        declared_files = set(generated.metadata.generated_files)
        emitted_files = set(generated.files)
        _validate_plugin_file_contract(emitted_files, declared_files)
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
            *_ENGINE_OWNED_FILES,
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

    file_results: list[dict[str, Any]] = []

    for filename, content in generated.files.items():
        result = write_plugin_generated_file(
            workspace_name=workspace,
            filename=filename,
            content=content,
            overwrite=False,
            allowed_filenames=declared_files,
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

    report_result = write_plugin_generated_file(
        workspace_name=workspace,
        filename="validation-report.md",
        content=report,
        overwrite=False,
        allowed_filenames=set(_ENGINE_OWNED_FILES),
    )

    return {
        "status": validation["status"],
        "stage": "complete",
        "plan": plan.to_dict(),
        "workspace": workspace_result,
        "files": file_results,
        "diagnostics": generated.diagnostics,
        "validation": validation,
        "validation_report": report_result,
        "deployment_performed": False,
        "message": (
            "Generation and local validation completed. "
            "No infrastructure was deployed."
        ),
    }


def generate_intelligent_gcs_project(**kwargs: Any) -> dict[str, Any]:
    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project("gcs", workspace_name, kwargs)


def generate_intelligent_cloud_run_project(**kwargs: Any) -> dict[str, Any]:
    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project("cloud-run", workspace_name, kwargs)


def generate_intelligent_gke_project(**kwargs: Any) -> dict[str, Any]:
    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project("gke", workspace_name, kwargs)

def generate_intelligent_cloud_sql_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a Cloud SQL project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "cloud-sql",
        workspace_name,
        kwargs,
    )


def generate_intelligent_network_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a private networking foundation project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "network",
        workspace_name,
        kwargs,
    )


def generate_intelligent_secret_manager_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a Secret Manager project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "secret-manager",
        workspace_name,
        kwargs,
    )


def generate_intelligent_iam_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate an IAM foundation project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "iam",
        workspace_name,
        kwargs,
    )


def generate_intelligent_cloud_functions_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a Cloud Functions (2nd gen) project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "cloud-functions",
        workspace_name,
        kwargs,
    )


def generate_intelligent_pubsub_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a Pub/Sub project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "pubsub",
        workspace_name,
        kwargs,
    )


def generate_intelligent_bigquery_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate a BigQuery project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "bigquery",
        workspace_name,
        kwargs,
    )

def generate_intelligent_artifact_registry_project(
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate and validate an Artifact Registry project."""

    workspace_name = kwargs.pop("workspace_name")
    return generate_service_project(
        "artifact-registry",
        workspace_name,
        kwargs,
    )

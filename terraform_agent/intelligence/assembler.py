"""Project Assembler: composes multiple generator plugins into one workspace.

Unlike a single-service generator, the assembler invokes several generator
plugins for one architecture request and composes their output as local
Terraform modules under ``modules/`` inside a single generated workspace,
wiring cross-service references (for example the VPC self-link, the
Serverless VPC Access connector, and the Cloud SQL connection name)
between the module blocks in the generated root module.
"""

from __future__ import annotations

from typing import Any

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.base.renderer import render_template
from terraform_agent.generators.base.validation import (
    normalize_label_value,
    require_non_empty,
    validate_workspace_name,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER
from terraform_agent.intelligence.assembler_templates import (
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.intelligence.engine import _validate_plugin_file_contract
from terraform_agent.intelligence.models import ResourcePlan
from terraform_agent.intelligence.registry import get_generator
from terraform_agent.intelligence.reporting import build_validation_report
from terraform_agent.tools.file_tools import (
    write_module_file,
    write_plugin_generated_file,
)
from terraform_agent.tools.terraform_tools import terraform_full_validation
from terraform_agent.tools.workspace_tools import create_workspace


_ENGINE_OWNED_FILES = frozenset({"validation-report.md"})
_MODULE_SERVICES = ("network", "cloud-sql", "secret-manager", "cloud-run")
_VPC_CONNECTOR_NAME_MAX_LENGTH = 25


def assemble_private_cloud_run_cloud_sql_project(
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
    Assemble a private Cloud Run + Cloud SQL platform from four generators.

    Invokes the network, cloud-sql, secret-manager, and cloud-run
    generator plugins, composes their output as local Terraform modules
    inside one workspace, wires the cross-service references between
    them, and runs a single local validation pass across the assembled
    tree. Nothing is deployed. Cloud Run manages its own dedicated
    runtime service account and IAM bindings, so the standalone IAM
    generator is not part of this recipe.
    """

    try:
        workspace = validate_workspace_name(workspace_name)
        region = require_non_empty(region, "region")
        environment = normalize_label_value(environment, "environment")
        owner = normalize_label_value(owner, "owner")
        application = normalize_label_value(application, "application")

        network_name = require_non_empty(
            network_name or f"{application}-vpc", "network_name"
        )
        service_name = require_non_empty(
            service_name or application, "service_name"
        )
        container_image = require_non_empty(
            container_image
            or (
                f"{region}-docker.pkg.dev/your-project/your-repository/"
                f"{service_name}:latest"
            ),
            "container_image",
        )
        database_secret_id = require_non_empty(
            database_secret_id, "database_secret_id"
        )
    except ValueError as exc:
        return {
            "status": "error",
            "stage": "analysis",
            "message": str(exc),
            "deployment_performed": False,
        }

    vpc_connector_name = f"{network_name}-connector"[
        :_VPC_CONNECTOR_NAME_MAX_LENGTH
    ]

    module_values = {
        "network": {
            "region": region,
            "network_name": network_name,
            "subnet_name": f"{network_name}-subnet",
            "subnet_cidr": subnet_cidr,
            "vpc_connector_name": vpc_connector_name,
        },
        "cloud-sql": {
            "region": region,
            "instance_name": f"{service_name}-db",
            "database_version": database_version,
            "tier": db_tier,
            "availability_type": db_availability_type,
            "environment": environment,
            "owner": owner,
            "application": application,
        },
        "secret-manager": {
            "region": region,
            "secret_ids": [database_secret_id],
            "environment": environment,
            "owner": owner,
            "application": application,
        },
        "cloud-run": {
            "region": region,
            "service_name": service_name,
            "container_image": container_image,
            "container_port": container_port,
            "allow_unauthenticated": allow_unauthenticated,
            "environment": environment,
            "owner": owner,
            "application": application,
        },
    }

    generated_by_service: dict[str, Any] = {}
    combined_resources: list[str] = []
    combined_features: set[str] = set()

    try:
        for service in _MODULE_SERVICES:
            generator = get_generator(service)
            generated = generator.generate(
                GeneratorContext(
                    workspace_name=workspace,
                    values=module_values[service],
                )
            )
            declared_files = set(generated.metadata.generated_files)
            emitted_files = set(generated.files)
            _validate_plugin_file_contract(emitted_files, declared_files)

            generated_by_service[service] = generated
            module_alias = service.replace("-", "_")
            combined_resources.extend(
                f"module.{module_alias}.{resource}"
                for resource in generated.metadata.resources
            )
            combined_features.update(generated.metadata.supported_features)
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "stage": "generation",
            "message": str(exc),
            "deployment_performed": False,
        }

    workspace_result = create_workspace(
        service="architecture", workspace_name=workspace
    )
    if workspace_result["status"] != "success":
        return {
            "status": "error",
            "stage": "workspace_creation",
            "workspace": workspace_result,
            "deployment_performed": False,
        }

    file_results: list[dict[str, Any]] = []

    for service, generated in generated_by_service.items():
        for filename, content in generated.files.items():
            if filename == "providers.tf":
                # Child modules must not declare their own provider block;
                # only the assembled root module configures the provider.
                continue

            result = write_module_file(
                workspace_name=workspace,
                module_name=service,
                filename=filename,
                content=content,
                allowed_filenames=set(generated.metadata.generated_files),
            )
            file_results.append(result)

            if result["status"] != "success":
                return {
                    "status": "error",
                    "stage": "file_generation",
                    "workspace": workspace_result,
                    "files": file_results,
                    "deployment_performed": False,
                }

    root_template_values = {
        "terraform_version": GOOGLE_PROVIDER[
            "terraform_version_constraint"
        ],
        "provider_source": GOOGLE_PROVIDER["source"],
        "provider_version": GOOGLE_PROVIDER["version_constraint"],
        "region": region,
        "environment": environment,
        "owner": owner,
        "application": application,
        "network_name": network_name,
        "subnet_cidr": subnet_cidr,
        "database_version": database_version,
        "db_tier": db_tier,
        "db_availability_type": db_availability_type,
        "database_secret_id": database_secret_id,
        "service_name": service_name,
        "container_image": container_image,
        "container_port": str(container_port),
        "allow_unauthenticated": str(allow_unauthenticated).lower(),
    }

    root_files = {
        "versions.tf": render_template(
            VERSIONS_TEMPLATE, root_template_values
        ),
        "variables.tf": render_template(
            VARIABLES_TEMPLATE, root_template_values
        ),
        "main.tf": render_template(MAIN_TEMPLATE, root_template_values),
        "outputs.tf": render_template(
            OUTPUTS_TEMPLATE, root_template_values
        ),
        "terraform.tfvars.example": render_template(
            TFVARS_TEMPLATE, root_template_values
        ),
        "README.md": render_template(
            README_TEMPLATE, root_template_values
        ),
    }

    root_declared_files = set(root_files) | _ENGINE_OWNED_FILES

    for filename, content in root_files.items():
        result = write_plugin_generated_file(
            workspace_name=workspace,
            filename=filename,
            content=content,
            overwrite=False,
            allowed_filenames=root_declared_files,
        )
        file_results.append(result)

        if result["status"] != "success":
            return {
                "status": "error",
                "stage": "file_generation",
                "workspace": workspace_result,
                "files": file_results,
                "deployment_performed": False,
            }

    validation = terraform_full_validation(workspace)

    module_files = tuple(
        f"modules/{service}/{filename}"
        for service, generated in generated_by_service.items()
        for filename in generated.files
        if filename != "providers.tf"
    )

    plan = ResourcePlan(
        service="private-cloud-run-cloud-sql",
        workspace_name=workspace,
        resources=tuple(combined_resources),
        generated_files=(
            *root_files,
            *module_files,
            *_ENGINE_OWNED_FILES,
        ),
        security_controls=tuple(sorted(combined_features)),
        request={
            "workspace_name": workspace,
            "region": region,
            "environment": environment,
            "owner": owner,
            "application": application,
            "network_name": network_name,
            "database_version": database_version,
            "service_name": service_name,
            "database_secret_id": database_secret_id,
        },
    )

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
        "architecture_type": "private-cloud-run-cloud-sql",
        "plan": plan.to_dict(),
        "workspace": workspace_result,
        "files": file_results,
        "validation": validation,
        "validation_report": report_result,
        "deployment_performed": False,
        "message": (
            "Multi-service architecture assembled and locally validated "
            "as one composed workspace using local Terraform modules. "
            "No infrastructure was deployed."
        ),
    }

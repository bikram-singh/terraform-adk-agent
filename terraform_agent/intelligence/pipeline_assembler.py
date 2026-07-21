"""Project Assembler recipe: BigQuery + Pub/Sub + Cloud Functions event
pipeline.

Composes three generator plugins into one workspace using local Terraform
modules, the same pattern as
:func:`terraform_agent.intelligence.assembler.assemble_private_cloud_run_cloud_sql_project`.
Unlike that recipe, the cross-module wiring here relies on Cloud
Functions' native Pub/Sub ``event_trigger`` (added specifically to support
this recipe) rather than a hand-wired push subscription, so no
``google_pubsub_subscription`` is generated: Eventarc manages its own
underlying subscription automatically.
"""

from __future__ import annotations

from typing import Any

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.base.renderer import render_template
from terraform_agent.generators.base.validation import (
    normalize_label_value,
    require_non_empty,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER
from terraform_agent.intelligence.engine import _validate_plugin_file_contract
from terraform_agent.intelligence.models import ResourcePlan
from terraform_agent.intelligence.pipeline_assembler_templates import (
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.intelligence.registry import get_generator
from terraform_agent.intelligence.reporting import build_validation_report
from terraform_agent.tools.file_tools import (
    write_module_file,
    write_plugin_generated_file,
)
from terraform_agent.tools.terraform_tools import terraform_full_validation
from terraform_agent.tools.workspace_tools import create_workspace


_ENGINE_OWNED_FILES = frozenset({"validation-report.md"})
_MODULE_SERVICES = ("pubsub", "cloud-functions", "bigquery")


def assemble_bigquery_pubsub_pipeline(
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
    deletion_protection: bool = True,
) -> dict[str, Any]:
    """
    Assemble a BigQuery + Pub/Sub + Cloud Functions event pipeline from
    three generators.

    Invokes the pubsub, cloud-functions, and bigquery generator plugins,
    composes their output as local Terraform modules inside one
    workspace, wires the cross-service references between them, and runs
    a single local validation pass across the assembled tree. Nothing is
    deployed. Cloud Functions manages its own dedicated runtime service
    account, so the standalone IAM generator is not part of this recipe;
    that same runtime service account is granted `roles/bigquery.dataEditor`
    on the BigQuery dataset directly.

    This generator does not write your function's application code --
    only the infrastructure (topic, Pub/Sub-triggered function, dataset)
    and the IAM wiring between them. You still need to provide a zipped
    function source (via `source_archive_path` in the generated tfvars)
    that reads the incoming Pub/Sub message and inserts a row into
    BigQuery.
    """

    try:
        workspace = require_non_empty(workspace_name, "workspace_name")
        region = require_non_empty(region, "region")
        environment = normalize_label_value(environment, "environment")
        owner = normalize_label_value(owner, "owner")
        application = normalize_label_value(application, "application")

        topic_name = require_non_empty(
            topic_name or f"{application}-events", "topic_name"
        )
        dataset_id = require_non_empty(
            dataset_id or application.replace("-", "_"), "dataset_id"
        )
        table_id = require_non_empty(table_id, "table_id")
        function_name = require_non_empty(
            function_name or f"{application}-processor", "function_name"
        )
        source_bucket_name = require_non_empty(
            source_bucket_name or f"{function_name}-source",
            "source_bucket_name",
        )
    except ValueError as exc:
        return {
            "status": "error",
            "stage": "analysis",
            "message": str(exc),
            "deployment_performed": False,
        }

    module_values = {
        "pubsub": {
            "region": region,
            "topics": [topic_name],
            "subscriptions": {},
            "environment": environment,
            "owner": owner,
            "application": application,
        },
        "cloud-functions": {
            "region": region,
            "function_name": function_name,
            "source_bucket_name": source_bucket_name,
            "runtime": runtime,
            "entry_point": entry_point,
            # A generation-time placeholder only: the root template
            # overrides this with the real
            # module.pubsub.topic_ids[var.topic_name] reference. A
            # generator-level value is still required here so this
            # module's own standalone generate() call validates cleanly.
            "trigger_type": "PUBSUB",
            "pubsub_trigger_topic": (
                f"projects/your-project/topics/{topic_name}"
            ),
            "environment": environment,
            "owner": owner,
            "application": application,
        },
        "bigquery": {
            "region": region,
            "dataset_id": dataset_id,
            "deletion_protection": deletion_protection,
            "tables": {
                table_id: {
                    "schema_json": (
                        '[{"name": "id", "type": "STRING", '
                        '"mode": "REQUIRED"}, {"name": "created_at", '
                        '"type": "TIMESTAMP", "mode": "REQUIRED"}]'
                    ),
                    "description": (
                        "Pipeline events written by the Cloud "
                        "Function. Replace with your own schema."
                    ),
                    "partitioning_field": "created_at",
                }
            },
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
                # Child modules must not declare their own provider
                # block; only the assembled root module configures it.
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
        "topic_name": topic_name,
        "dataset_id": dataset_id,
        "table_id": table_id,
        "deletion_protection": str(deletion_protection).lower(),
        "function_name": function_name,
        "source_bucket_name": source_bucket_name,
        "runtime": runtime,
        "entry_point": entry_point,
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
        service="bigquery-pubsub-cloud-functions-pipeline",
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
            "topic_name": topic_name,
            "dataset_id": dataset_id,
            "table_id": table_id,
            "function_name": function_name,
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
        "architecture_type": "bigquery-pubsub-cloud-functions-pipeline",
        "plan": plan.to_dict(),
        "workspace": workspace_result,
        "files": file_results,
        "validation": validation,
        "validation_report": report_result,
        "deployment_performed": False,
        "message": (
            "Multi-service event pipeline assembled and locally validated "
            "as one composed workspace using local Terraform modules. "
            "No infrastructure was deployed."
        ),
    }

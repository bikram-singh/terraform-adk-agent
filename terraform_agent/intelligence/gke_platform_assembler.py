"""Project Assembler recipe: GKE + Network + IAM Workload Identity
platform.

Composes the GKE and IAM generator plugins into one workspace, plus a
hand-written network + firewall setup at the root level (see the module
docstring in :mod:`gke_platform_assembler_templates` for why the
standalone Network generator isn't reused here). The IAM module creates
a dedicated service account for application *workloads* -- distinct from
GKE's own node service account -- bound via Workload Identity Federation.
"""

from __future__ import annotations

from typing import Any

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.base.renderer import (
    render_default_assignment,
    render_hcl_string_list,
    render_template,
)
from terraform_agent.generators.base.validation import (
    normalize_label_value,
    require_non_empty,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER
from terraform_agent.intelligence.engine import _validate_plugin_file_contract
from terraform_agent.intelligence.gke_platform_assembler_templates import (
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
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
_MODULE_SERVICES = ("gke", "iam")


def assemble_gke_workload_identity_platform(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "platform",
    network_name: str = "",
    subnet_cidr: str = "10.20.0.0/22",
    pods_cidr: str = "10.24.0.0/14",
    services_cidr: str = "10.28.0.0/20",
    master_ipv4_cidr_block: str = "172.16.0.0/28",
    cluster_name: str = "",
    node_machine_type: str = "e2-standard-4",
    node_min_count: int = 1,
    node_max_count: int = 3,
    workload_service_account_id: str = "",
    workload_project_roles: list[str] | None = None,
    k8s_namespace: str = "default",
    k8s_service_account: str = "",
    gke_deletion_protection: bool = True,
) -> dict[str, Any]:
    """
    Assemble a private GKE cluster with a Workload Identity-bound
    application platform in one call.

    Invokes the gke and iam generator plugins, composes their output as
    local Terraform modules inside one workspace, and wires a
    hand-written network + firewall setup (not the standalone Network
    generator, which creates Private Service Access and a Serverless VPC
    Access connector that GKE doesn't need) around them. The IAM module's
    service account is distinct from GKE's own node service account: it
    is meant for application workloads running as pods, bound via
    `roles/iam.workloadIdentityUser` so the Kubernetes ServiceAccount
    named by `k8s_service_account` (in `k8s_namespace`) can impersonate
    it to call GCP APIs. Nothing is deployed.
    """

    try:
        workspace = require_non_empty(workspace_name, "workspace_name")
        region = require_non_empty(region, "region")
        environment = normalize_label_value(environment, "environment")
        owner = normalize_label_value(owner, "owner")
        application = normalize_label_value(application, "application")

        network_name = require_non_empty(
            network_name or f"{application}-vpc", "network_name"
        )
        cluster_name = require_non_empty(
            cluster_name or f"{application}-gke", "cluster_name"
        )
        workload_service_account_id = require_non_empty(
            workload_service_account_id or f"{application}-workload",
            "workload_service_account_id",
        )
        k8s_service_account = require_non_empty(
            k8s_service_account or f"{application}-ksa",
            "k8s_service_account",
        )

        roles = list(workload_project_roles or ["roles/logging.logWriter"])
        if not roles:
            raise ValueError(
                "workload_project_roles must contain at least one entry."
            )
    except ValueError as exc:
        return {
            "status": "error",
            "stage": "analysis",
            "message": str(exc),
            "deployment_performed": False,
        }

    module_values = {
        "gke": {
            "region": region,
            "cluster_name": cluster_name,
            "node_machine_type": node_machine_type,
            "node_min_count": node_min_count,
            "node_max_count": node_max_count,
            # network/subnetwork/pods_secondary_range_name/
            # services_secondary_range_name are NOT processed by the GKE
            # generator's Python side at all (bare Terraform variables
            # with no default) -- the root template overrides them with
            # real references to the hand-written network resources.
            # deletion_protection IS Python-processed, so it's set here
            # to the safe production default; the root template does
            # not override it, so this value is what actually deploys.
            "deletion_protection": gke_deletion_protection,
            "environment": environment,
            "owner": owner,
            "application": application,
        },
        "iam": {
            "region": region,
            "service_account_id": workload_service_account_id,
            "project_roles": roles,
            # impersonators/impersonation_role are set by the root
            # template (Workload Identity binding needs the real
            # project_id, only known at apply time via var.project_id).
            "impersonators": [],
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
            module_alias = "iam_workload" if service == "iam" else service
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
        "subnet_name": f"{network_name}-subnet",
        "subnet_cidr": subnet_cidr,
        "pods_cidr": pods_cidr,
        "services_cidr": services_cidr,
        "master_ipv4_cidr_block": master_ipv4_cidr_block,
        "cluster_name": cluster_name,
        "node_machine_type": node_machine_type,
        "node_min_count": node_min_count,
        "node_max_count": node_max_count,
        "workload_service_account_id": workload_service_account_id,
        "workload_project_roles": render_hcl_string_list(roles),
        "workload_project_roles_default_line": render_default_assignment(
            render_hcl_string_list(roles)
        ),
        "k8s_namespace": k8s_namespace,
        "k8s_service_account": k8s_service_account,
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
        service="gke-network-iam-workload-identity-platform",
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
            "cluster_name": cluster_name,
            "workload_service_account_id": workload_service_account_id,
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
        "architecture_type": "gke-network-iam-workload-identity-platform",
        "plan": plan.to_dict(),
        "workspace": workspace_result,
        "files": file_results,
        "validation": validation,
        "validation_report": report_result,
        "deployment_performed": False,
        "message": (
            "GKE + Network + IAM Workload Identity platform assembled "
            "and locally validated as one composed workspace using "
            "local Terraform modules. No infrastructure was deployed."
        ),
    }

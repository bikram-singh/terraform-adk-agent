"""Approved tools exposed by the Terraform Platform Agent."""

from terraform_agent.tools.architecture_tools import (
    plan_terraform_architecture,
)
from terraform_agent.tools.architect_tools import (
    design_infrastructure_platform,
)
from terraform_agent.tools.assembler_tools import (
    assemble_private_cloud_run_postgres_platform,
    assemble_event_driven_data_pipeline,
    assemble_gke_platform,
)
from terraform_agent.tools.drift_tools import (
    detect_infrastructure_drift,
)
from terraform_agent.tools.policy_tools import (
    check_policy_compliance,
)
from terraform_agent.tools.cost_tools import (
    estimate_workspace_cost,
)
from terraform_agent.tools.registry_tools import (
    list_available_infrastructure_modules,
)
from terraform_agent.tools.file_tools import (
    list_generated_files,
    read_generated_file,
    write_generated_file,
)
from terraform_agent.tools.project_tools import (
    generate_artifact_registry_terraform_project,
    generate_gcs_terraform_project,
    generate_cloud_run_terraform_project,
    generate_cloud_sql_terraform_project,
    generate_gke_terraform_project,
    generate_iam_terraform_project,
    generate_network_terraform_project,
    generate_secret_manager_terraform_project,
    generate_cloud_functions_terraform_project,
    generate_pubsub_terraform_project,
    generate_bigquery_terraform_project,
)

from terraform_agent.tools.terraform_tools import (
    terraform_apply,
    terraform_format,
    terraform_full_validation,
    terraform_initialize,
    terraform_plan,
    terraform_validate,
)

from terraform_agent.tools.workspace_tools import (
    create_workspace,
    list_workspaces,
)

__all__ = [
    "plan_terraform_architecture",
    "design_infrastructure_platform",
    "assemble_private_cloud_run_postgres_platform",
    "assemble_event_driven_data_pipeline",
    "assemble_gke_platform",
    "detect_infrastructure_drift",
    "check_policy_compliance",
    "list_available_infrastructure_modules",
    "estimate_workspace_cost",
    "generate_artifact_registry_terraform_project",
    "generate_gcs_terraform_project",
    "generate_cloud_sql_terraform_project",
    "generate_cloud_run_terraform_project",
    "generate_gke_terraform_project",
    "generate_network_terraform_project",
    "generate_secret_manager_terraform_project",
    "generate_iam_terraform_project",
    "generate_cloud_functions_terraform_project",
    "generate_pubsub_terraform_project",
    "generate_bigquery_terraform_project",
    "create_workspace",
    "list_workspaces",
    "write_generated_file",
    "read_generated_file",
    "list_generated_files",
    "terraform_format",
    "terraform_initialize",
    "terraform_validate",
    "terraform_full_validation",
    "terraform_plan",
    "terraform_apply",
]

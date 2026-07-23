"""Terraform MCP Server: exposes a curated, safety-scoped subset of this
agent's tools over the Model Context Protocol (MCP), so any MCP client
(Claude Desktop, Claude Code, or any other MCP-compatible tool) can use
them directly -- not just through the ADK agent runtime.

Every tool registered here is a direct, unmodified wrap of an existing,
already-tested function elsewhere in this project -- there is no new
generation, validation, or infrastructure logic in this module.

Deliberately narrow scope: this server exposes generation, local
validation, drift *detection* (read-only), policy compliance, cost
estimation, and module discovery -- nothing that can create, modify, or
destroy real infrastructure. terraform_apply, terraform_plan against
real state, and any state read/write are NOT exposed here. An MCP
client is a different trust boundary than a human directly in the ADK
chat loop reviewing and approving each step, so real deployment stays
scoped to that more supervised path for now, not to arbitrary MCP
callers.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)
from terraform_agent.intelligence.gke_platform_assembler import (
    assemble_gke_workload_identity_platform,
)
from terraform_agent.intelligence.pipeline_assembler import (
    assemble_bigquery_pubsub_pipeline,
)
from terraform_agent.tools.architect_tools import (
    design_infrastructure_platform,
)
from terraform_agent.tools.architecture_tools import (
    plan_terraform_architecture,
)
from terraform_agent.tools.cost_tools import estimate_workspace_cost
from terraform_agent.tools.drift_tools import detect_infrastructure_drift
from terraform_agent.tools.policy_tools import check_policy_compliance
from terraform_agent.tools.project_tools import (
    generate_artifact_registry_terraform_project,
    generate_bigquery_terraform_project,
    generate_cloud_functions_terraform_project,
    generate_cloud_run_terraform_project,
    generate_cloud_sql_terraform_project,
    generate_gcs_terraform_project,
    generate_gke_terraform_project,
    generate_iam_terraform_project,
    generate_network_terraform_project,
    generate_pubsub_terraform_project,
    generate_secret_manager_terraform_project,
)
from terraform_agent.tools.registry_tools import (
    list_available_infrastructure_modules,
)
from terraform_agent.tools.workspace_tools import list_workspaces


mcp = FastMCP(
    name="terraform-adk-agent",
    instructions=(
        "Generates and locally validates complete Terraform projects "
        "for Google Cloud (11 standalone services, 3 composed "
        "architectures), checks generated workspaces for policy "
        "compliance and drift against real GCP state, and estimates "
        "rough monthly cost for provisioned resources. Never deploys, "
        "modifies, or destroys real infrastructure through this "
        "server -- generation, local validation, and read-only checks "
        "only."
    ),
)


# Single-service generators. Each wraps an existing, independently
# tested generate_*_terraform_project function -- no new logic here.
mcp.tool()(generate_gcs_terraform_project)
mcp.tool()(generate_cloud_run_terraform_project)
mcp.tool()(generate_cloud_sql_terraform_project)
mcp.tool()(generate_gke_terraform_project)
mcp.tool()(generate_network_terraform_project)
mcp.tool()(generate_secret_manager_terraform_project)
mcp.tool()(generate_iam_terraform_project)
mcp.tool()(generate_cloud_functions_terraform_project)
mcp.tool()(generate_pubsub_terraform_project)
mcp.tool()(generate_bigquery_terraform_project)
mcp.tool()(generate_artifact_registry_terraform_project)

# Composed architectures and the natural-language entry point.
mcp.tool()(assemble_private_cloud_run_cloud_sql_project)
mcp.tool()(assemble_bigquery_pubsub_pipeline)
mcp.tool()(assemble_gke_workload_identity_platform)
mcp.tool()(design_infrastructure_platform)
mcp.tool()(plan_terraform_architecture)

# Governance: policy, drift (read-only), cost, and module discovery.
mcp.tool()(check_policy_compliance)
mcp.tool()(detect_infrastructure_drift)
mcp.tool()(estimate_workspace_cost)
mcp.tool()(list_available_infrastructure_modules)
mcp.tool()(list_workspaces)


def main() -> None:
    """Entry point for running this MCP server over stdio transport."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

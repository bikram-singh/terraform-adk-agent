"""Unit tests for the Terraform MCP Server's tool registration.

These test registration and the safety boundary (which tools are and
are not exposed), not MCP protocol mechanics -- the mcp SDK's own test
suite already covers that.
"""

from __future__ import annotations

import asyncio

from terraform_agent.mcp_server.server import mcp


EXPECTED_TOOL_NAMES = {
    "generate_gcs_terraform_project",
    "generate_cloud_run_terraform_project",
    "generate_cloud_sql_terraform_project",
    "generate_gke_terraform_project",
    "generate_network_terraform_project",
    "generate_secret_manager_terraform_project",
    "generate_iam_terraform_project",
    "generate_cloud_functions_terraform_project",
    "generate_pubsub_terraform_project",
    "generate_bigquery_terraform_project",
    "generate_artifact_registry_terraform_project",
    "assemble_private_cloud_run_cloud_sql_project",
    "assemble_bigquery_pubsub_pipeline",
    "assemble_gke_workload_identity_platform",
    "design_infrastructure_platform",
    "plan_terraform_architecture",
    "check_policy_compliance",
    "detect_infrastructure_drift",
    "estimate_workspace_cost",
    "list_available_infrastructure_modules",
    "list_workspaces",
}

# Anything that can create, modify, or destroy real infrastructure, or
# read/write raw Terraform state, must never appear here -- this is the
# actual safety boundary this whole module exists to enforce.
DISALLOWED_TOOL_NAMES = {
    "terraform_apply",
    "terraform_plan",
    "terraform_initialize",
    "terraform_full_validation",
    "terraform_validate",
    "terraform_format",
    "write_generated_file",
    "read_generated_file",
    "create_workspace",
}


def _registered_tool_names() -> set[str]:
    tools = asyncio.run(mcp.list_tools())
    return {tool.name for tool in tools}


def test_all_expected_tools_are_registered() -> None:
    registered = _registered_tool_names()
    assert EXPECTED_TOOL_NAMES.issubset(registered)


def test_registered_tool_count_matches_expected_exactly() -> None:
    """A stricter check than issubset: catches an accidental extra tool
    being exposed just as readily as a missing one."""

    registered = _registered_tool_names()
    assert registered == EXPECTED_TOOL_NAMES


def test_no_deployment_or_state_mutating_tools_are_exposed() -> None:
    registered = _registered_tool_names()
    assert not (DISALLOWED_TOOL_NAMES & registered)


def test_a_registered_tool_is_actually_callable() -> None:
    result = asyncio.run(
        mcp.call_tool("list_available_infrastructure_modules", {})
    )

    assert result is not None

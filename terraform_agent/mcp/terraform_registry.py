"""ADK client integration for HashiCorp's official Terraform MCP Server."""

from __future__ import annotations

import os

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

DEFAULT_IMAGE = "hashicorp/terraform-mcp-server:1.0.0"

REGISTRY_TOOLS = [
    "search_providers",
    "get_provider_details",
    "get_latest_provider_version",
    "search_modules",
    "get_module_details",
    "get_latest_module_version",
    "search_policies",
    "get_policy_details",
]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def terraform_mcp_enabled() -> bool:
    """Return whether the Terraform MCP integration is enabled."""

    return _env_bool("TERRAFORM_MCP_ENABLED", False)


def terraform_mcp_server_parameters() -> StdioServerParameters:
    """Build safe, registry-only Docker stdio server parameters."""

    image = os.getenv("TERRAFORM_MCP_DOCKER_IMAGE", DEFAULT_IMAGE)

    return StdioServerParameters(
        command="docker",
        args=[
            "run",
            "-i",
            "--rm",
            "-e",
            "ENABLE_TF_OPERATIONS=false",
            image,
            "--toolsets=registry",
        ],
    )


def build_terraform_mcp_toolset() -> McpToolset | None:
    """Build the registry-only Terraform MCP toolset when enabled."""

    if not terraform_mcp_enabled():
        return None

    timeout = int(os.getenv("TERRAFORM_MCP_TIMEOUT_SECONDS", "60"))

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=terraform_mcp_server_parameters(),
            timeout=timeout,
        ),
        tool_filter=REGISTRY_TOOLS,
    )

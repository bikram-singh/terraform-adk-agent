"""Unit tests for the v0.7 Terraform MCP configuration."""

from terraform_agent.mcp.terraform_registry import (
    DEFAULT_IMAGE,
    REGISTRY_TOOLS,
    terraform_mcp_server_parameters,
)


def test_mcp_uses_docker_stdio() -> None:
    params = terraform_mcp_server_parameters()
    assert params.command == "docker"
    assert params.args[:3] == ["run", "-i", "--rm"]


def test_mcp_is_registry_only_and_operations_disabled() -> None:
    params = terraform_mcp_server_parameters()
    assert "--toolsets=registry" in params.args
    assert "ENABLE_TF_OPERATIONS=false" in params.args
    assert DEFAULT_IMAGE in params.args


def test_mcp_tool_filter_is_read_only_registry_scope() -> None:
    assert set(REGISTRY_TOOLS) == {
        "search_providers",
        "get_provider_details",
        "get_latest_provider_version",
        "search_modules",
        "get_module_details",
        "get_latest_module_version",
        "search_policies",
        "get_policy_details",
    }

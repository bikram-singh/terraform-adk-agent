"""Low-level, read-only client for the Terraform Registry MCP toolset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from terraform_agent.mcp.terraform_registry import (
    terraform_mcp_server_parameters,
)


@dataclass(frozen=True)
class RegistryToolResponse:
    """Normalized result returned by one Terraform Registry MCP tool."""

    tool_name: str
    arguments: Mapping[str, Any]
    text: str
    is_error: bool


def _content_to_text(result: CallToolResult) -> str:
    """Convert MCP content blocks into plain text for controlled processing."""

    parts: list[str] = []

    for item in result.content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
            continue

        resource = getattr(item, "resource", None)
        resource_text = getattr(resource, "text", None)
        if isinstance(resource_text, str):
            parts.append(resource_text)
            continue

        try:
            parts.append(json.dumps(item.model_dump(), default=str))
        except Exception:
            parts.append(str(item))

    return "\n".join(parts)


async def list_registry_tools() -> dict[str, dict[str, Any]]:
    """Return the current tool schemas exposed by the Registry MCP server."""

    server_params = terraform_mcp_server_parameters()

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()

    return {
        tool.name: dict(tool.inputSchema or {})
        for tool in result.tools
    }


async def call_registry_tool(
    tool_name: str,
    arguments: Mapping[str, Any],
) -> RegistryToolResponse:
    """Call one read-only Terraform Registry MCP tool."""

    server_params = terraform_mcp_server_parameters()

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                tool_name,
                arguments=dict(arguments),
            )

    return RegistryToolResponse(
        tool_name=tool_name,
        arguments=dict(arguments),
        text=_content_to_text(result),
        is_error=bool(result.isError),
    )

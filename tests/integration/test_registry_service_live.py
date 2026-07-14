"""Optional live integration test for Terraform MCP Registry service."""

from __future__ import annotations

import asyncio
import os

import pytest

from terraform_agent.services.terraform_registry import (
    get_terraform_provider_version,
)


@pytest.mark.skipif(
    os.getenv("RUN_TERRAFORM_MCP_INTEGRATION") != "true",
    reason="Set RUN_TERRAFORM_MCP_INTEGRATION=true for the Docker MCP test.",
)
def test_live_provider_version_lookup() -> None:
    result = asyncio.run(get_terraform_provider_version())

    assert result["status"] == "success"
    assert result["external_links_removed"] is True
    assert result["deployment_performed"] is False

"""Unit tests for the v0.7.2 Terraform Registry service layer."""

import asyncio

from terraform_agent.mcp.client import RegistryToolResponse
from terraform_agent.services import terraform_registry


def test_sanitizer_removes_external_links() -> None:
    value = (
        "Read [documentation](https://registry.terraform.io/example) "
        "or visit https://example.invalid/path."
    )

    cleaned = terraform_registry.sanitize_registry_text(value)

    assert "https://" not in cleaned
    assert "documentation" in cleaned
    assert "[external-link-removed]" in cleaned


def test_schema_argument_selection_is_forward_compatible() -> None:
    schema = {
        "type": "object",
        "properties": {
            "provider_namespace": {"type": "string"},
            "provider_name": {"type": "string"},
        },
    }

    result = terraform_registry._arguments_for_schema(
        schema,
        {
            "namespace": "hashicorp",
            "provider_namespace": "hashicorp",
            "name": "google",
            "provider_name": "google",
        },
    )

    assert result == {
        "provider_namespace": "hashicorp",
        "provider_name": "google",
    }


def test_document_id_is_extracted_from_json() -> None:
    value = '{"results": [{"id": "12683339", "title": "resource"}]}'

    assert terraform_registry._extract_document_id(value) == "12683339"


def test_provider_version_service_returns_sanitized_structure(
    monkeypatch,
) -> None:
    async def fake_list_tools():
        return {
            "get_latest_provider_version": {
                "properties": {
                    "namespace": {},
                    "name": {},
                }
            }
        }

    async def fake_call(tool_name, arguments):
        return RegistryToolResponse(
            tool_name=tool_name,
            arguments=arguments,
            text=(
                "Latest version is 7.39.0. "
                "See https://registry.terraform.io/providers/hashicorp/google."
            ),
            is_error=False,
        )

    monkeypatch.setattr(
        terraform_registry,
        "list_registry_tools",
        fake_list_tools,
    )
    monkeypatch.setattr(
        terraform_registry,
        "call_registry_tool",
        fake_call,
    )

    result = asyncio.run(
        terraform_registry.get_terraform_provider_version()
    )

    assert result["status"] == "success"
    assert "7.39.0" in result["content"]
    assert "https://" not in result["content"]
    assert result["external_links_removed"] is True

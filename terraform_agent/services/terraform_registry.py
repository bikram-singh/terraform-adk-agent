"""Structured, sanitized Terraform Registry service backed by MCP."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from terraform_agent.mcp.client import (
    RegistryToolResponse,
    call_registry_tool,
    list_registry_tools,
)


_URL_PATTERN = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s<>()\[\]{}]+"
)
_MARKDOWN_LINK_PATTERN = re.compile(
    r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)",
    re.IGNORECASE,
)
_DOCUMENT_ID_PATTERNS = (
    re.compile(r'"id"\s*:\s*"([^"]+)"'),
    re.compile(r"\bid\s*[:=]\s*[`'\"]?([A-Za-z0-9_-]+)", re.IGNORECASE),
)


def sanitize_registry_text(
    value: str,
    *,
    max_characters: int = 7000,
) -> str:
    """
    Remove URI payloads and constrain untrusted Registry documentation.

    The readable link label is retained, but link destinations are removed.
    """

    cleaned = _MARKDOWN_LINK_PATTERN.sub(r"\1", value)
    cleaned = _URL_PATTERN.sub("[external-link-removed]", cleaned)
    cleaned = cleaned.replace("\x00", "")

    safe_lines: list[str] = []
    for line in cleaned.splitlines():
        normalized = line.strip()
        if not normalized:
            safe_lines.append("")
            continue

        lower = normalized.lower()
        if "javascript:" in lower or "data:text/" in lower:
            continue

        safe_lines.append(line.rstrip())

    compact = "\n".join(safe_lines).strip()
    if len(compact) > max_characters:
        compact = (
            compact[:max_characters].rstrip()
            + "\n[registry-content-truncated]"
        )

    return compact


def _schema_properties(schema: Mapping[str, Any]) -> set[str]:
    properties = schema.get("properties", {})
    if isinstance(properties, Mapping):
        return {str(key) for key in properties}
    return set()


def _arguments_for_schema(
    schema: Mapping[str, Any],
    candidates: Mapping[str, Any],
) -> dict[str, Any]:
    """Select only arguments accepted by the currently exposed tool schema."""

    accepted = _schema_properties(schema)
    return {
        key: value
        for key, value in candidates.items()
        if key in accepted and value is not None
    }


def _extract_document_id(value: str) -> str | None:
    """Extract a provider-document identifier from search output."""

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None

    def walk(item: Any) -> str | None:
        if isinstance(item, Mapping):
            for key in ("id", "document_id", "provider_doc_id"):
                candidate = item.get(key)
                if candidate is not None:
                    return str(candidate)
            for child in item.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(item, list):
            for child in item:
                found = walk(child)
                if found:
                    return found
        return None

    found = walk(parsed)
    if found:
        return found

    for pattern in _DOCUMENT_ID_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)

    return None


def _structured_result(
    *,
    operation: str,
    provider_namespace: str,
    provider_name: str,
    query: str | None,
    response: RegistryToolResponse,
) -> dict[str, Any]:
    return {
        "status": "error" if response.is_error else "success",
        "source": "terraform-registry-via-mcp",
        "operation": operation,
        "provider_namespace": provider_namespace,
        "provider_name": provider_name,
        "query": query,
        "content": sanitize_registry_text(response.text),
        "external_links_removed": True,
        "deployment_performed": False,
    }


async def get_terraform_provider_version(
    provider_namespace: str = "hashicorp",
    provider_name: str = "google",
) -> dict[str, Any]:
    """
    Get the latest Terraform provider version through the Registry MCP server.

    The result is sanitized and contains no active external URI payloads.
    """

    schemas = await list_registry_tools()
    schema = schemas.get("get_latest_provider_version", {})

    arguments = _arguments_for_schema(
        schema,
        {
            "namespace": provider_namespace,
            "provider_namespace": provider_namespace,
            "name": provider_name,
            "provider_name": provider_name,
        },
    )

    response = await call_registry_tool(
        "get_latest_provider_version",
        arguments,
    )

    return _structured_result(
        operation="latest-provider-version",
        provider_namespace=provider_namespace,
        provider_name=provider_name,
        query=None,
        response=response,
    )


async def get_terraform_resource_guidance(
    resource_name: str,
    provider_namespace: str = "hashicorp",
    provider_name: str = "google",
) -> dict[str, Any]:
    """
    Retrieve sanitized provider documentation for a Terraform resource.

    The service discovers the live MCP schemas, searches provider documents,
    resolves the returned document ID, retrieves details, removes external
    URI payloads, and returns bounded structured content.
    """

    resource_name = resource_name.strip()
    if not resource_name:
        return {
            "status": "error",
            "message": "resource_name must not be empty.",
            "deployment_performed": False,
        }

    schemas = await list_registry_tools()

    search_schema = schemas.get("search_providers", {})
    search_arguments = _arguments_for_schema(
        search_schema,
        {
            "service_name": resource_name,
            "query": resource_name,
            "resource_name": resource_name,
            "namespace": provider_namespace,
            "provider_namespace": provider_namespace,
            "name": provider_name,
            "provider_name": provider_name,
        },
    )

    search_response = await call_registry_tool(
        "search_providers",
        search_arguments,
    )
    if search_response.is_error:
        return _structured_result(
            operation="search-provider-documentation",
            provider_namespace=provider_namespace,
            provider_name=provider_name,
            query=resource_name,
            response=search_response,
        )

    document_id = _extract_document_id(search_response.text)
    if not document_id:
        return {
            "status": "error",
            "source": "terraform-registry-via-mcp",
            "operation": "resolve-provider-document",
            "provider_namespace": provider_namespace,
            "provider_name": provider_name,
            "query": resource_name,
            "message": (
                "The Registry search completed, but no provider document ID "
                "could be resolved from the structured response."
            ),
            "search_summary": sanitize_registry_text(
                search_response.text,
                max_characters=2500,
            ),
            "external_links_removed": True,
            "deployment_performed": False,
        }

    detail_schema = schemas.get("get_provider_details", {})
    detail_arguments = _arguments_for_schema(
        detail_schema,
        {
            "id": document_id,
            "document_id": document_id,
            "provider_doc_id": document_id,
        },
    )

    detail_response = await call_registry_tool(
        "get_provider_details",
        detail_arguments,
    )

    result = _structured_result(
        operation="provider-resource-guidance",
        provider_namespace=provider_namespace,
        provider_name=provider_name,
        query=resource_name,
        response=detail_response,
    )
    result["document_id"] = document_id
    return result

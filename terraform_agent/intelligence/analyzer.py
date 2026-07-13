"""Requirement normalization and validation."""

from __future__ import annotations

import re

from terraform_agent.intelligence.models import GCSRequest


_WORKSPACE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$")
_LABEL_PATTERN = re.compile(r"^[a-z0-9_-]{1,63}$")


def _required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _workspace(value: str) -> str:
    cleaned = _required(value, "workspace_name")
    if not _WORKSPACE_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "workspace_name must be 3-80 characters and contain only "
            "letters, numbers, hyphens, or underscores."
        )
    return cleaned


def _label(value: str, field_name: str) -> str:
    cleaned = value.strip().lower().replace(" ", "-")
    if not _LABEL_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"{field_name} must be 1-63 characters and contain only "
            "lower-case letters, numbers, hyphens, or underscores."
        )
    return cleaned


def analyze_gcs_request(
    workspace_name: str,
    region: str = "asia-south1",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "terraform-adk-agent",
    noncurrent_version_retention_days: int = 30,
) -> GCSRequest:
    """Normalize natural-language tool arguments into a GCS request."""

    if noncurrent_version_retention_days < 1:
        raise ValueError(
            "noncurrent_version_retention_days must be at least 1."
        )

    return GCSRequest(
        workspace_name=_workspace(workspace_name),
        region=_required(region, "region"),
        environment=_label(environment, "environment"),
        owner=_label(owner, "owner"),
        application=_label(application, "application"),
        noncurrent_version_retention_days=(
            noncurrent_version_retention_days
        ),
    )

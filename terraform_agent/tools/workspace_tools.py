"""Safe workspace management for generated Terraform configurations."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from terraform_agent.config import get_settings


SAFE_WORKSPACE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$")


def _validate_workspace_name(workspace_name: str) -> str:
    """Validate a workspace name before it is used in a filesystem path."""

    cleaned = workspace_name.strip()

    if not SAFE_WORKSPACE_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Workspace name must be 3-80 characters and contain only "
            "letters, numbers, hyphens, or underscores."
        )

    return cleaned


def _ensure_inside_output_root(path: Path) -> Path:
    """Ensure a resolved path remains inside the generated output root."""

    settings = get_settings()
    output_root = settings.output_root
    resolved = path.resolve()

    try:
        resolved.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(
            f"Path is outside the approved output directory: {resolved}"
        ) from exc

    return resolved


def generate_workspace_name(service: str) -> str:
    """Generate a unique workspace name for one Terraform request."""

    safe_service = re.sub(r"[^a-zA-Z0-9_-]", "-", service.strip().lower())
    safe_service = safe_service.strip("-_") or "terraform"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(3)

    return f"{timestamp}-{safe_service}-{suffix}"


def get_workspace_path(workspace_name: str) -> Path:
    """Return a validated absolute workspace path."""

    settings = get_settings()
    valid_name = _validate_workspace_name(workspace_name)

    return _ensure_inside_output_root(settings.output_root / valid_name)


def create_workspace(
    service: str,
    workspace_name: str = "",
) -> dict[str, Any]:
    """
    Create an isolated Terraform workspace.

    Args:
        service: Supported service such as gcs, cloud-run, or bigquery.
        workspace_name: Optional custom workspace name.

    Returns:
        Details about the created workspace.
    """

    name = (
        _validate_workspace_name(workspace_name)
        if workspace_name.strip()
        else generate_workspace_name(service)
    )

    workspace = get_workspace_path(name)

    if workspace.exists() and any(workspace.iterdir()):
        return {
            "status": "error",
            "workspace_name": name,
            "message": (
                "Workspace already exists and contains files. A "
                "previous request was not overwritten."
            ),
        }

    workspace.mkdir(parents=True, exist_ok=True)

    return {
        "status": "success",
        "workspace_name": name,
        "workspace_path": str(workspace),
        "service": service,
        "message": "Isolated Terraform workspace created.",
    }


def list_workspaces() -> dict[str, Any]:
    """List generated Terraform workspaces."""

    settings = get_settings()

    workspaces = sorted(
        path.name
        for path in settings.output_root.iterdir()
        if path.is_dir()
    )

    return {
        "status": "success",
        "count": len(workspaces),
        "workspaces": workspaces,
    }
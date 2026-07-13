"""Restricted file operations for generated Terraform workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from terraform_agent.tools.workspace_tools import (
    get_workspace_path,
)


ALLOWED_TERRAFORM_FILES = {
    "main.tf",
    "variables.tf",
    "outputs.tf",
    "versions.tf",
    "providers.tf",
    "locals.tf",
    "iam.tf",
    "service-account.tf",
    "terraform.tfvars.example",
    "schema.json",
    "README.md",
    "validation-report.md",
}


def _validate_filename(filename: str) -> str:
    """Validate that a requested filename is explicitly allowed."""

    cleaned = Path(filename.strip()).name

    if cleaned != filename.strip():
        raise ValueError("Nested file paths are not allowed.")

    if cleaned not in ALLOWED_TERRAFORM_FILES:
        raise ValueError(
            f"File '{cleaned}' is not allowed. "
            f"Allowed files: {sorted(ALLOWED_TERRAFORM_FILES)}"
        )

    return cleaned


def write_generated_file(
    workspace_name: str,
    filename: str,
    content: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Write an approved file inside a generated Terraform workspace.

    Args:
        workspace_name: Existing workspace name.
        filename: Approved Terraform or documentation filename.
        content: Complete file content.
        overwrite: Whether an existing file may be replaced.

    Returns:
        File-writing result.
    """

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    approved_filename = _validate_filename(filename)
    target = (workspace / approved_filename).resolve()

    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected path outside the approved workspace.",
        }

    if target.exists() and not overwrite:
        return {
            "status": "error",
            "message": (
                f"File already exists: {approved_filename}. "
                "Set overwrite=true only when replacement is intentional."
            ),
        }

    target.write_text(content, encoding="utf-8", newline="\n")

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "filename": approved_filename,
        "path": str(target),
        "bytes_written": target.stat().st_size,
    }


def read_generated_file(
    workspace_name: str,
    filename: str,
) -> dict[str, Any]:
    """
    Read an approved file from a generated Terraform workspace.

    Args:
        workspace_name: Existing workspace name.
        filename: Approved filename.

    Returns:
        File contents and metadata.
    """

    workspace = get_workspace_path(workspace_name)
    approved_filename = _validate_filename(filename)
    target = (workspace / approved_filename).resolve()

    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected path outside the approved workspace.",
        }

    if not target.exists() or not target.is_file():
        return {
            "status": "error",
            "message": f"File does not exist: {approved_filename}",
        }

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "filename": approved_filename,
        "content": target.read_text(encoding="utf-8"),
    }


def list_generated_files(workspace_name: str) -> dict[str, Any]:
    """List approved files currently present in a workspace."""

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    files = sorted(
        path.name
        for path in workspace.iterdir()
        if path.is_file() and path.name in ALLOWED_TERRAFORM_FILES
    )

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "count": len(files),
        "files": files,
    }
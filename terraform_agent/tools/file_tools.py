"""Secure file operations for generated Terraform workspaces."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from terraform_agent.tools.workspace_tools import get_workspace_path


_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ALLOWED_SUFFIXES = {".tf", ".md", ".json"}
_ALLOWED_EXACT_FILENAMES = {"terraform.tfvars.example", "terraform.tfvars"}
_MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def _validate_safe_filename(filename: str) -> str:
    """Validate filesystem safety and approved generated-file types."""

    requested = filename.strip()

    if not requested:
        raise ValueError("Filename must not be empty.")

    path = Path(requested)

    if path.is_absolute():
        raise ValueError("Absolute file paths are not allowed.")

    cleaned = path.name

    if cleaned != requested:
        raise ValueError("Nested file paths are not allowed.")

    if cleaned.startswith("."):
        raise ValueError("Hidden files are not allowed.")

    if not _SAFE_FILENAME_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "Filename contains unsupported characters or is too long."
        )

    if (
        cleaned not in _ALLOWED_EXACT_FILENAMES
        and Path(cleaned).suffix.lower() not in _ALLOWED_SUFFIXES
    ):
        raise ValueError(
            "Only flat Terraform, Markdown, JSON, or "
            "terraform.tfvars.example files are allowed."
        )

    return cleaned


def _write_file(
    workspace_name: str,
    filename: str,
    content: str,
    overwrite: bool,
    allowed_filenames: set[str] | None,
) -> dict[str, Any]:
    """
    Internal secure writer.

    This function is not exposed directly to ADK, so its internal policy
    argument does not become part of an ADK/Pydantic tool schema.
    """

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    try:
        approved_filename = _validate_safe_filename(filename)
    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

    if (
        allowed_filenames is not None
        and approved_filename not in allowed_filenames
    ):
        return {
            "status": "error",
            "message": (
                f"File '{approved_filename}' is not declared by this "
                f"generator. Declared files: {sorted(allowed_filenames)}"
            ),
        }

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

    target.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "filename": approved_filename,
        "path": str(target),
        "bytes_written": target.stat().st_size,
    }


def write_generated_file(
    workspace_name: str,
    filename: str,
    content: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Write a safe Terraform or documentation file.

    This is the public ADK tool. Plugin-owned file authorization is enforced
    internally by write_plugin_generated_file.
    """

    return _write_file(
        workspace_name=workspace_name,
        filename=filename,
        content=content,
        overwrite=overwrite,
        allowed_filenames=None,
    )


def write_plugin_generated_file(
    workspace_name: str,
    filename: str,
    content: str,
    allowed_filenames: set[str],
    overwrite: bool = False,
) -> dict[str, Any]:
    """Write a file authorized by the selected generator plugin."""

    return _write_file(
        workspace_name=workspace_name,
        filename=filename,
        content=content,
        overwrite=overwrite,
        allowed_filenames=allowed_filenames,
    )


def write_module_file(
    workspace_name: str,
    module_name: str,
    filename: str,
    content: str,
    allowed_filenames: set[str],
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Write a generator-owned file under modules/<module_name>/ in a workspace.

    Reserved for the Project Assembler, which composes multiple generator
    plugins into one workspace using local Terraform modules. Not exposed
    directly to ADK.
    """

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    cleaned_module_name = module_name.strip()
    if not _MODULE_NAME_PATTERN.fullmatch(cleaned_module_name):
        return {
            "status": "error",
            "message": f"Invalid module_name: {module_name}",
        }

    try:
        approved_filename = _validate_safe_filename(filename)
    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

    if approved_filename not in allowed_filenames:
        return {
            "status": "error",
            "message": (
                f"File '{approved_filename}' is not declared by this "
                f"generator. Declared files: {sorted(allowed_filenames)}"
            ),
        }

    workspace_resolved = workspace.resolve()
    module_dir = (workspace_resolved / "modules" / cleaned_module_name)

    try:
        module_dir.resolve().relative_to(workspace_resolved)
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected path outside the approved workspace.",
        }

    target = (module_dir / approved_filename).resolve()

    try:
        target.relative_to(workspace_resolved)
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected path outside the approved workspace.",
        }

    module_dir.mkdir(parents=True, exist_ok=True)

    if target.exists() and not overwrite:
        return {
            "status": "error",
            "message": (
                f"File already exists: modules/{cleaned_module_name}/"
                f"{approved_filename}. Set overwrite=true only when "
                "replacement is intentional."
            ),
        }

    target.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "module_name": cleaned_module_name,
        "filename": approved_filename,
        "path": str(target),
        "bytes_written": target.stat().st_size,
    }


def read_generated_file(
    workspace_name: str,
    filename: str,
) -> dict[str, Any]:
    """Read a safe file from an existing generated workspace."""

    workspace = get_workspace_path(workspace_name)

    try:
        approved_filename = _validate_safe_filename(filename)
    except ValueError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }

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


def list_generated_files(
    workspace_name: str,
) -> dict[str, Any]:
    """List safe generated files currently present in a workspace."""

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    files: list[str] = []

    for path in workspace.iterdir():
        if not path.is_file():
            continue

        try:
            _validate_safe_filename(path.name)
        except ValueError:
            continue

        files.append(path.name)

    files.sort()

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "count": len(files),
        "files": files,
    }
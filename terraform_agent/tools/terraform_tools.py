"""Restricted Terraform CLI tools for formatting and validation."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from terraform_agent.config import get_settings
from terraform_agent.tools.workspace_tools import get_workspace_path


def _run_terraform_command(
    workspace_name: str,
    arguments: list[str],
) -> dict[str, Any]:
    """
    Execute a predefined Terraform command inside an approved workspace.

    This function is private so the ADK agent cannot supply arbitrary
    commands or shell syntax.
    """

    settings = get_settings()
    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "command": arguments,
            "message": f"Workspace does not exist: {workspace_name}",
        }

    command = [settings.terraform_executable, *arguments]
    started = time.monotonic()

    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.terraform_command_timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return {
            "status": "error",
            "command": command,
            "message": (
                "Terraform executable was not found. "
                "Check TERRAFORM_EXECUTABLE and PATH."
            ),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "error",
            "command": command,
            "message": (
                "Terraform command exceeded the configured timeout of "
                f"{settings.terraform_command_timeout} seconds."
            ),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }

    duration = round(time.monotonic() - started, 3)

    return {
        "status": "success" if completed.returncode == 0 else "error",
        "workspace_name": workspace_name,
        "command": command,
        "return_code": completed.returncode,
        "duration_seconds": duration,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def terraform_format(workspace_name: str) -> dict[str, Any]:
    """
    Format Terraform configuration files in a workspace.

    Runs only: terraform fmt -recursive
    """

    return _run_terraform_command(
        workspace_name,
        ["fmt", "-recursive"],
    )


def terraform_initialize(workspace_name: str) -> dict[str, Any]:
    """
    Initialize Terraform without configuring a remote backend.

    Runs only:
    terraform init -backend=false -input=false -no-color
    """

    return _run_terraform_command(
        workspace_name,
        [
            "init",
            "-backend=false",
            "-input=false",
            "-no-color",
        ],
    )


def terraform_validate(workspace_name: str) -> dict[str, Any]:
    """
    Validate Terraform configuration in a workspace.

    Runs only:
    terraform validate -no-color
    """

    return _run_terraform_command(
        workspace_name,
        ["validate", "-no-color"],
    )


def terraform_full_validation(workspace_name: str) -> dict[str, Any]:
    """
    Run format, initialization, and validation in sequence.

    Stops after a failed initialization because validation may require
    provider plugins installed by terraform init.
    """

    format_result = terraform_format(workspace_name)
    init_result = terraform_initialize(workspace_name)

    if init_result["status"] != "success":
        return {
            "status": "error",
            "workspace_name": workspace_name,
            "format": format_result,
            "initialize": init_result,
            "validate": {
                "status": "skipped",
                "message": "Validation skipped because initialization failed.",
            },
        }

    validate_result = terraform_validate(workspace_name)

    overall_status = (
        "success"
        if format_result["status"] == "success"
        and init_result["status"] == "success"
        and validate_result["status"] == "success"
        else "error"
    )

    return {
        "status": overall_status,
        "workspace_name": workspace_name,
        "format": format_result,
        "initialize": init_result,
        "validate": validate_result,
        "deployment_performed": False,
        "message": (
            "Terraform formatting and local validation completed. "
            "No infrastructure was deployed."
        ),
    }
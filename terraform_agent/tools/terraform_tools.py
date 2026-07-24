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
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Execute a predefined Terraform command inside an approved workspace.

    This function is private so the ADK agent cannot supply arbitrary
    commands or shell syntax. timeout_seconds overrides the configured
    default for this single call -- useful for operations on resources
    known to take much longer than average (for example GKE clusters,
    which have taken upward of 15 minutes in real live testing).
    """

    settings = get_settings()
    workspace = get_workspace_path(workspace_name)
    effective_timeout = timeout_seconds or settings.terraform_command_timeout

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
            timeout=effective_timeout,
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
                f"{effective_timeout} seconds. If this operation involves "
                "a resource known to take a long time (GKE, Cloud SQL), "
                "retry with a larger timeout_seconds value."
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


def terraform_plan(
    workspace_name: str,
    var_file: str = "terraform.tfvars",
    destroy: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Create a real Terraform execution plan for human review.

    This connects to the real Google Cloud project configured for the
    workspace's provider and reads live state. It does not create,
    modify, or destroy anything by itself.

    Requires TERRAFORM_ALLOW_APPLY=true in the environment (or
    TERRAFORM_ALLOW_DESTROY=true when destroy=True), and a real
    var_file (typically terraform.tfvars, not the .example placeholder)
    already present in the workspace with reviewed, real values such as
    the actual project_id.

    Produces a saved plan file (tfplan or tfplan-destroy) that must be
    reviewed by the user before terraform_apply is called with the same
    plan_file. Never call terraform_apply automatically after this in
    the same turn; always show the plan output and wait for explicit
    user confirmation first.

    timeout_seconds overrides the configured default (1800s) for both
    the init and plan steps in this call, if planning against a large
    or slow-to-refresh architecture needs more time than usual.
    """

    settings = get_settings()
    required_flag = (
        settings.terraform_allow_destroy
        if destroy
        else settings.terraform_allow_apply
    )
    flag_name = (
        "TERRAFORM_ALLOW_DESTROY" if destroy else "TERRAFORM_ALLOW_APPLY"
    )

    if not required_flag:
        return {
            "status": "error",
            "message": (
                f"Real deployment is disabled. Set {flag_name}=true in "
                ".env and restart the agent process to enable this "
                "operation."
            ),
            "deployment_performed": False,
        }

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
            "deployment_performed": False,
        }

    var_file_path = (workspace / var_file).resolve()
    try:
        var_file_path.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected var_file path outside the workspace.",
            "deployment_performed": False,
        }

    if not var_file_path.exists():
        return {
            "status": "error",
            "message": (
                f"'{var_file}' does not exist in workspace "
                f"'{workspace_name}'. Copy terraform.tfvars.example to "
                f"{var_file}, fill in real reviewed values such as the "
                "actual project_id, then try again."
            ),
            "deployment_performed": False,
        }

    init_result = _run_terraform_command(
        workspace_name,
        ["init", "-input=false", "-no-color"],
        timeout_seconds=timeout_seconds,
    )

    if init_result["status"] != "success":
        return {
            "status": "error",
            "workspace_name": workspace_name,
            "initialize": init_result,
            "message": "Terraform initialization failed before planning.",
            "deployment_performed": False,
        }

    plan_file = "tfplan-destroy" if destroy else "tfplan"
    plan_arguments = ["plan", "-input=false", "-no-color"]
    if destroy:
        plan_arguments.append("-destroy")
    plan_arguments.extend([f"-var-file={var_file}", f"-out={plan_file}"])

    plan_result = _run_terraform_command(
        workspace_name, plan_arguments, timeout_seconds=timeout_seconds
    )

    return {
        "status": plan_result["status"],
        "workspace_name": workspace_name,
        "initialize": init_result,
        "plan": plan_result,
        "plan_file": plan_file,
        "deployment_performed": False,
        "message": (
            "Plan created against real Google Cloud state. Review the "
            "plan output carefully with the user before calling "
            "terraform_apply with the same plan_file. Nothing has been "
            "created, modified, or destroyed yet."
        ),
    }


def terraform_apply(
    workspace_name: str,
    plan_file: str = "tfplan",
    destroy: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """
    Apply a previously created and human-reviewed Terraform plan file.

    This creates, modifies, or destroys real Google Cloud infrastructure
    and may incur real cost. Only ever call this after terraform_plan
    has been run in the same workspace and the user has explicitly
    reviewed the plan output and confirmed, in this conversation, that
    they want to proceed. Never call this in the same turn as
    terraform_plan without that explicit confirmation.

    Requires TERRAFORM_ALLOW_APPLY=true in the environment (or
    TERRAFORM_ALLOW_DESTROY=true when destroy=True matches a destroy
    plan) and an existing plan_file produced by terraform_plan.

    timeout_seconds overrides the configured default (1800s) for this
    call. Pass a larger value (for example 2400-3600) when the plan
    includes a GKE cluster, a new Cloud SQL instance, or any other
    resource documented as slow in this project's real live-testing
    history -- these have taken 10-15+ minutes to actually complete.
    """

    settings = get_settings()
    required_flag = (
        settings.terraform_allow_destroy
        if destroy
        else settings.terraform_allow_apply
    )
    flag_name = (
        "TERRAFORM_ALLOW_DESTROY" if destroy else "TERRAFORM_ALLOW_APPLY"
    )

    if not required_flag:
        return {
            "status": "error",
            "message": (
                f"Real deployment is disabled. Set {flag_name}=true in "
                ".env and restart the agent process to enable this "
                "operation."
            ),
            "deployment_performed": False,
        }

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
            "deployment_performed": False,
        }

    plan_path = (workspace / plan_file).resolve()
    try:
        plan_path.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected plan_file path outside the workspace.",
            "deployment_performed": False,
        }

    if not plan_path.exists():
        return {
            "status": "error",
            "message": (
                f"Plan file '{plan_file}' does not exist in workspace "
                f"'{workspace_name}'. Call terraform_plan first and "
                "review its output with the user before applying."
            ),
            "deployment_performed": False,
        }

    apply_result = _run_terraform_command(
        workspace_name,
        ["apply", "-input=false", "-no-color", plan_file],
        timeout_seconds=timeout_seconds,
    )

    return {
        "status": apply_result["status"],
        "workspace_name": workspace_name,
        "apply": apply_result,
        "deployment_performed": apply_result["status"] == "success",
        "message": (
            "Real infrastructure change applied. Cloud resources may "
            "have been created, modified, or destroyed."
            if apply_result["status"] == "success"
            else "Apply failed. Review the error above; Terraform "
            "state reflects only what actually succeeded."
        ),
    }
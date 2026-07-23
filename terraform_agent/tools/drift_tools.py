"""Drift detection: compare real Google Cloud state against what
Terraform last recorded, without proposing or applying any changes.
"""

from __future__ import annotations

import json
from typing import Any

from terraform_agent.tools.terraform_tools import _run_terraform_command
from terraform_agent.tools.workspace_tools import get_workspace_path


_NO_OP_ACTION_SETS = (["no-op"], [])


def _extract_changed_attributes(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Return the sorted set of attribute names whose value differs
    between the recorded (before) and real, refreshed (after) state."""

    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def _parse_drifted_resources(plan_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract drifted resources from a `terraform show -json` payload
    produced from a `-refresh-only` plan."""

    drifted_resources: list[dict[str, Any]] = []

    for resource_change in plan_json.get("resource_changes", []):
        change = resource_change.get("change", {})
        actions = change.get("actions", [])

        if actions in _NO_OP_ACTION_SETS:
            continue

        before = change.get("before") or {}
        after = change.get("after") or {}

        drifted_resources.append(
            {
                "address": resource_change.get("address"),
                "resource_type": resource_change.get("type"),
                "actions": actions,
                "changed_attributes": _extract_changed_attributes(
                    before, after
                ),
            }
        )

    return drifted_resources


def build_drift_report(
    workspace_name: str, drifted_resources: list[dict[str, Any]]
) -> str:
    """Build a short, human-readable drift report."""

    if not drifted_resources:
        return (
            f"# Drift Report: {workspace_name}\n\n"
            "No drift detected. Live Google Cloud state matches what "
            "Terraform last recorded for every resource in this "
            "workspace.\n"
        )

    lines = [
        f"# Drift Report: {workspace_name}",
        "",
        f"**{len(drifted_resources)} resource(s) have changed outside "
        "Terraform** since it last recorded their state. Nothing has "
        "been changed or reconciled -- this is a report only.",
        "",
    ]

    for resource in drifted_resources:
        lines.append(f"## `{resource['address']}`")
        lines.append("")
        lines.append(f"- Action Terraform would take to reconcile: "
                      f"`{', '.join(resource['actions'])}`")

        if resource["changed_attributes"]:
            lines.append("- Attributes that changed:")
            lines.extend(
                f"  - `{attribute}`"
                for attribute in resource["changed_attributes"]
            )
        else:
            lines.append(
                "- Attributes changed: none reported (resource-level "
                "change only, e.g. tainted or replaced out-of-band)."
            )

        lines.append("")

    return "\n".join(lines)


def detect_infrastructure_drift(
    workspace_name: str,
    var_file: str = "terraform.tfvars",
) -> dict[str, Any]:
    """
    Detect drift between real Google Cloud state and what this
    workspace's Terraform state last recorded, without proposing or
    applying any changes.

    Runs `terraform init` followed by `terraform plan -refresh-only`,
    which reads live state from the real Google Cloud project
    configured in the workspace and compares it against Terraform's own
    records, with no attempt to reconcile the two. This is read-only
    with respect to both Google Cloud and the local Terraform state
    file: creating a saved refresh-only plan does not persist anything
    by itself -- only applying that plan would, and this tool never
    does that. Unlike terraform_plan, this does not require
    TERRAFORM_ALLOW_APPLY, since no create, modify, or destroy action is
    ever proposed or performed.

    Requires a real var_file (typically terraform.tfvars, not the
    .example placeholder) already present in the workspace with
    reviewed, real values such as the actual project_id, and valid
    Application Default Credentials for that real project.
    """

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    var_file_path = (workspace / var_file).resolve()
    try:
        var_file_path.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected var_file path outside the workspace.",
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
        }

    init_result = _run_terraform_command(
        workspace_name,
        ["init", "-input=false", "-no-color"],
    )

    if init_result["status"] != "success":
        return {
            "status": "error",
            "workspace_name": workspace_name,
            "initialize": init_result,
            "message": (
                "Terraform initialization failed before checking for "
                "drift."
            ),
        }

    plan_file = "drift-check.tfplan"

    plan_result = _run_terraform_command(
        workspace_name,
        [
            "plan",
            "-refresh-only",
            "-input=false",
            "-no-color",
            f"-var-file={var_file}",
            f"-out={plan_file}",
            "-detailed-exitcode",
        ],
    )

    # -detailed-exitcode semantics: 0 = no drift, 1 = error,
    # 2 = drift detected. _run_terraform_command reports non-zero exit
    # codes as status="error", so this checks return_code directly
    # rather than the summarized status field.
    return_code = plan_result.get("return_code")

    if return_code not in (0, 2):
        return {
            "status": "error",
            "workspace_name": workspace_name,
            "initialize": init_result,
            "plan": plan_result,
            "message": (
                "Drift check failed. See plan.stderr for details."
            ),
        }

    show_result = _run_terraform_command(
        workspace_name,
        ["show", "-json", "-no-color", plan_file],
    )

    drifted_resources: list[dict[str, Any]] = []

    if show_result["status"] == "success" and show_result["stdout"]:
        try:
            plan_json = json.loads(show_result["stdout"])
        except json.JSONDecodeError:
            plan_json = {}

        drifted_resources = _parse_drifted_resources(plan_json)

    has_drift = bool(drifted_resources)
    report = build_drift_report(workspace_name, drifted_resources)

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "drift_detected": has_drift,
        "drifted_resource_count": len(drifted_resources),
        "drifted_resources": drifted_resources,
        "plan_file": plan_file,
        "report": report,
        "message": (
            f"Drift check complete. {len(drifted_resources)} resource(s) "
            "have changed outside Terraform since it last recorded "
            "their state."
            if has_drift
            else (
                "Drift check complete. No drift detected -- live "
                "Google Cloud state matches what Terraform expects."
            )
        ),
    }

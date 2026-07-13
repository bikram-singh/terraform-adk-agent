"""Validation report rendering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from terraform_agent.intelligence.models import ResourcePlan


def _command_section(title: str, result: dict[str, Any]) -> str:
    stdout = result.get("stdout") or "No standard output."
    stderr = result.get("stderr") or "No standard error output."

    return (
        f"## {title}\n\n"
        f"- Status: `{result.get('status', 'unknown')}`\n"
        f"- Return code: `{result.get('return_code', 'N/A')}`\n"
        f"- Duration: `{result.get('duration_seconds', 'N/A')}` seconds\n\n"
        "### Standard output\n\n"
        "```text\n"
        f"{stdout}\n"
        "```\n\n"
        "### Standard error\n\n"
        "```text\n"
        f"{stderr}\n"
        "```\n"
    )


def build_validation_report(
    plan: ResourcePlan,
    validation: dict[str, Any],
) -> str:
    """Build validation-report.md without nested triple-quoted strings."""

    lines = [
        "# Terraform Validation Report",
        "",
        "## Summary",
        "",
        f"- Workspace: `{plan.workspace_name}`",
        f"- Service: `{plan.service}`",
        f"- Overall status: `{validation.get('status', 'unknown')}`",
        f"- Generated at: `{datetime.now(timezone.utc).isoformat()}`",
        "- Infrastructure deployed: `No`",
        "",
        "## Planned resources",
        "",
    ]

    lines.extend(f"- `{item}`" for item in plan.resources)
    lines.extend(["", "## Security controls", ""])
    lines.extend(f"- {item}" for item in plan.security_controls)
    lines.extend(
        [
            "",
            _command_section(
                "Terraform Format",
                validation.get("format", {}),
            ),
            _command_section(
                "Terraform Initialization",
                validation.get("initialize", {}),
            ),
            _command_section(
                "Terraform Validation",
                validation.get("validate", {}),
            ),
            "## Scope",
            "",
            "Only formatting, backend-disabled initialization, and local "
            "validation were performed.",
            "",
            "No plan, apply, destroy, import, or state modification occurred.",
            "",
            "Successful validation does not prove API enablement, IAM access, "
            "name availability, quota availability, or deployment success.",
            "",
        ]
    )

    return "\n".join(lines)

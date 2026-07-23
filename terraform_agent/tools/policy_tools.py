"""Lightweight Policy as Code: simple, offline compliance checks against
a generated workspace's Terraform variables.

Deliberately narrow in scope -- three checks, no external calls, no
Terraform binary or GCP credentials required. Runs instantly against
any generated workspace's tfvars file, before generate/apply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from terraform_agent.tools.workspace_tools import get_workspace_path


DEFAULT_REQUIRED_LABEL_KEYS: tuple[str, ...] = (
    "environment",
    "owner",
    "application",
)

DEFAULT_ALLOWED_REGIONS: tuple[str, ...] = (
    "asia-south1",
    "asia-south2",
    "us-central1",
    "us-east1",
    "us-east4",
    "us-west1",
)

# Lower-case letters, digits, and hyphens; must start with a letter and
# not end with a hyphen -- the same shape GCP itself requires for most
# resource name fields.
DEFAULT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")

# Only keys shaped like a real resource name are checked for naming
# convention -- this is a lightweight heuristic scan, not a full HCL
# parser or schema, so it deliberately stays conservative about what it
# inspects.
_NAME_LIKE_KEY_SUFFIXES = ("_name", "_id")
_NAME_LIKE_KEYS_EXCLUDED = frozenset({"project_id"})
_PLACEHOLDER_VALUES = frozenset({"your-project-id", "placeholder", "todo"})


@dataclass
class PolicyViolation:
    """A single policy check failure."""

    rule: str
    key: str
    value: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "key": self.key,
            "value": self.value,
            "message": self.message,
        }


def parse_tfvars(content: str) -> dict[str, str]:
    """Parse simple `key = "value"` / `key = value` lines from tfvars
    content.

    This is a lightweight scan, not a full HCL parser: list and map
    values are skipped entirely, since none of the three checks here
    need them, and reliably parsing arbitrary HCL collections isn't
    worth the complexity for this narrow a use case.
    """

    values: dict[str, str] = {}

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$", stripped)
        if not match:
            continue

        key, raw_value = match.group(1), match.group(2).strip()

        if raw_value.startswith("[") or raw_value.startswith("{"):
            continue

        if raw_value.startswith('"') and raw_value.endswith('"'):
            values[key] = raw_value[1:-1]
        else:
            values[key] = raw_value

    return values


def check_required_labels(
    values: dict[str, str],
    required_label_keys: tuple[str, ...] = DEFAULT_REQUIRED_LABEL_KEYS,
) -> list[PolicyViolation]:
    """Flag any required label key that's missing, empty, or still a
    generator placeholder value."""

    violations = []

    for key in required_label_keys:
        value = values.get(key, "").strip()

        if not value or value.lower() in _PLACEHOLDER_VALUES:
            violations.append(
                PolicyViolation(
                    rule="required_labels",
                    key=key,
                    value=value,
                    message=(
                        f"'{key}' is missing or still a placeholder "
                        "value."
                    ),
                )
            )

    return violations


def check_region_allowlist(
    values: dict[str, str],
    allowed_regions: tuple[str, ...] = DEFAULT_ALLOWED_REGIONS,
) -> list[PolicyViolation]:
    """Flag a region value that isn't in the allowed list, if a region
    is set at all."""

    violations = []
    region = values.get("region", "").strip()

    if region and region not in allowed_regions:
        violations.append(
            PolicyViolation(
                rule="region_allowlist",
                key="region",
                value=region,
                message=(
                    f"Region '{region}' is not in the allowed list: "
                    f"{', '.join(allowed_regions)}."
                ),
            )
        )

    return violations


def check_naming_convention(
    values: dict[str, str],
    name_pattern: re.Pattern[str] = DEFAULT_NAME_PATTERN,
) -> list[PolicyViolation]:
    """Flag any `*_name` / `*_id` value that doesn't match the naming
    pattern, skipping placeholders and excluded keys."""

    violations = []

    for key, value in values.items():
        if key in _NAME_LIKE_KEYS_EXCLUDED:
            continue

        if not any(
            key.endswith(suffix) for suffix in _NAME_LIKE_KEY_SUFFIXES
        ):
            continue

        if not value or value.lower() in _PLACEHOLDER_VALUES:
            continue

        if not name_pattern.fullmatch(value):
            violations.append(
                PolicyViolation(
                    rule="naming_convention",
                    key=key,
                    value=value,
                    message=(
                        f"'{key}' = '{value}' doesn't match the "
                        "required naming pattern: lowercase letters, "
                        "digits, and hyphens; must start with a "
                        "letter and not end with a hyphen."
                    ),
                )
            )

    return violations


def build_policy_report(
    workspace_name: str, violations: list[PolicyViolation]
) -> str:
    """Build a short, human-readable policy report."""

    if not violations:
        return (
            f"# Policy Report: {workspace_name}\n\n"
            "No policy violations found. Required labels are present, "
            "the region is on the allowed list, and name-like values "
            "follow the naming convention.\n"
        )

    lines = [
        f"# Policy Report: {workspace_name}",
        "",
        f"**{len(violations)} policy violation(s) found.**",
        "",
    ]

    violations_by_rule: dict[str, list[PolicyViolation]] = {}
    for violation in violations:
        violations_by_rule.setdefault(violation.rule, []).append(violation)

    for rule, rule_violations in violations_by_rule.items():
        lines.append(f"## {rule}")
        lines.append("")
        for violation in rule_violations:
            lines.append(f"- {violation.message}")
        lines.append("")

    return "\n".join(lines)


def check_policy_compliance(
    workspace_name: str,
    var_file: str = "terraform.tfvars.example",
    required_label_keys: tuple[str, ...] = DEFAULT_REQUIRED_LABEL_KEYS,
    allowed_regions: tuple[str, ...] = DEFAULT_ALLOWED_REGIONS,
) -> dict[str, Any]:
    """
    Check a generated workspace's Terraform variables against three
    lightweight policy rules: required labels present (not missing or a
    placeholder), region on the allowed list, and name-like values
    (any `*_name` or `*_id` variable) following a consistent naming
    convention.

    This is fully offline: no Terraform binary, no GCP credentials, no
    network calls -- it only reads and parses the workspace's own
    tfvars file, so it's safe to run before generate/apply as a fast
    sanity check, or against terraform.tfvars.example right after
    generation to catch generator-level defaults that would fail these
    same checks. Pass var_file="terraform.tfvars" to check real,
    reviewed values instead of the generator's defaults.

    This deliberately does not check GCP-specific validity (e.g.
    whether a region actually exists) or enforce organization-specific
    policy beyond these three rules -- it's a starting point, not a
    replacement for a real policy engine like OPA/Sentinel.
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
                f"'{workspace_name}'."
            ),
        }

    content = var_file_path.read_text(encoding="utf-8")
    values = parse_tfvars(content)

    violations: list[PolicyViolation] = []
    violations.extend(
        check_required_labels(values, required_label_keys)
    )
    violations.extend(check_region_allowlist(values, allowed_regions))
    violations.extend(check_naming_convention(values))

    report = build_policy_report(workspace_name, violations)

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "compliant": len(violations) == 0,
        "violation_count": len(violations),
        "violations": [violation.to_dict() for violation in violations],
        "report": report,
        "message": (
            "No policy violations found."
            if not violations
            else f"{len(violations)} policy violation(s) found."
        ),
    }

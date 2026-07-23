"""Unit tests for lightweight Policy as Code checks."""

from __future__ import annotations

from terraform_agent.tools.policy_tools import (
    check_naming_convention,
    check_policy_compliance,
    check_region_allowlist,
    check_required_labels,
    parse_tfvars,
)


SAMPLE_TFVARS = """
project_id = "your-project-id"
region     = "asia-south1"

environment = "dev"
owner       = "platform-team"
application = "verify-dp"

network_name = "verify-dp-vpc"
subnet_name  = "verify-dp-vpc-subnet"

node_min_count = 1
node_max_count = 3

workload_project_roles = [
    "roles/logging.logWriter",
]
"""


def test_parse_tfvars_extracts_scalar_values() -> None:
    values = parse_tfvars(SAMPLE_TFVARS)

    assert values["region"] == "asia-south1"
    assert values["environment"] == "dev"
    assert values["network_name"] == "verify-dp-vpc"
    assert values["node_min_count"] == "1"


def test_parse_tfvars_skips_lists_and_comments() -> None:
    values = parse_tfvars(SAMPLE_TFVARS)

    assert "workload_project_roles" not in values


def test_required_labels_pass_when_present() -> None:
    values = parse_tfvars(SAMPLE_TFVARS)

    assert check_required_labels(values) == []


def test_required_labels_flag_missing_key() -> None:
    values = {"environment": "dev", "owner": "platform-team"}

    violations = check_required_labels(values)

    assert len(violations) == 1
    assert violations[0].key == "application"


def test_required_labels_flag_placeholder_value() -> None:
    values = {
        "environment": "dev",
        "owner": "TODO",
        "application": "app",
    }

    violations = check_required_labels(values)

    assert len(violations) == 1
    assert violations[0].key == "owner"


def test_region_allowlist_passes_for_allowed_region() -> None:
    assert check_region_allowlist({"region": "asia-south1"}) == []


def test_region_allowlist_flags_disallowed_region() -> None:
    violations = check_region_allowlist({"region": "europe-west1"})

    assert len(violations) == 1
    assert violations[0].value == "europe-west1"


def test_region_allowlist_skips_when_no_region_set() -> None:
    assert check_region_allowlist({}) == []


def test_naming_convention_passes_for_valid_names() -> None:
    values = parse_tfvars(SAMPLE_TFVARS)

    assert check_naming_convention(values) == []


def test_naming_convention_flags_uppercase_name() -> None:
    violations = check_naming_convention({"cluster_name": "MyCluster"})

    assert len(violations) == 1
    assert violations[0].key == "cluster_name"


def test_naming_convention_flags_trailing_hyphen() -> None:
    violations = check_naming_convention({"network_name": "app-vpc-"})

    assert len(violations) == 1


def test_naming_convention_skips_project_id() -> None:
    violations = check_naming_convention(
        {"project_id": "your-project-id"}
    )

    assert violations == []


def test_naming_convention_ignores_non_name_keys() -> None:
    violations = check_naming_convention(
        {"node_machine_type": "e2-standard-4"}
    )

    assert violations == []


def test_check_policy_compliance_rejects_missing_workspace() -> None:
    result = check_policy_compliance("this-workspace-does-not-exist")

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_check_policy_compliance_rejects_missing_var_file(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "policy-test-workspace"
    workspace.mkdir()

    monkeypatch.setattr(
        "terraform_agent.tools.policy_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = check_policy_compliance("policy-test-workspace")

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_check_policy_compliance_passes_for_compliant_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "policy-test-workspace-2"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(SAMPLE_TFVARS)

    monkeypatch.setattr(
        "terraform_agent.tools.policy_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = check_policy_compliance("policy-test-workspace-2")

    assert result["status"] == "success"
    assert result["compliant"] is True
    assert result["violation_count"] == 0


def test_check_policy_compliance_reports_violations(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "policy-test-workspace-3"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'region = "europe-west1"\n'
        'environment = "dev"\n'
        'owner = "your-project-id"\n'
        'application = "App"\n'
        'cluster_name = "MyCluster"\n'
    )

    monkeypatch.setattr(
        "terraform_agent.tools.policy_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = check_policy_compliance("policy-test-workspace-3")

    assert result["status"] == "success"
    assert result["compliant"] is False
    # region (1) + owner placeholder (1) + application not required-label
    # violation but IS a required label present as non-placeholder value
    # "App" (only naming-checked if key ends in _name/_id, which
    # "application" does not) + cluster_name naming (1) = 3
    assert result["violation_count"] == 3
    rules = {violation["rule"] for violation in result["violations"]}
    assert rules == {
        "region_allowlist",
        "required_labels",
        "naming_convention",
    }

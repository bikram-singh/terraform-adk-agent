"""Unit tests for drift detection."""

from __future__ import annotations

import json
from unittest.mock import patch

from terraform_agent.tools.drift_tools import (
    build_drift_report,
    detect_infrastructure_drift,
    _parse_drifted_resources,
)


SAMPLE_REFRESH_ONLY_PLAN = {
    "resource_changes": [
        {
            "address": "google_compute_firewall.allow_internal",
            "type": "google_compute_firewall",
            "change": {
                "actions": ["update"],
                "before": {"source_ranges": ["10.0.0.0/20"]},
                "after": {"source_ranges": ["10.0.0.0/8"]},
            },
        },
        {
            "address": "google_compute_network.this",
            "type": "google_compute_network",
            "change": {
                "actions": ["no-op"],
                "before": {"name": "app-vpc"},
                "after": {"name": "app-vpc"},
            },
        },
    ]
}

SAMPLE_NO_DRIFT_PLAN = {
    "resource_changes": [
        {
            "address": "google_compute_network.this",
            "type": "google_compute_network",
            "change": {
                "actions": ["no-op"],
                "before": {"name": "app-vpc"},
                "after": {"name": "app-vpc"},
            },
        },
    ]
}


def test_parse_drifted_resources_skips_no_op_changes() -> None:
    drifted = _parse_drifted_resources(SAMPLE_REFRESH_ONLY_PLAN)

    assert len(drifted) == 1
    assert drifted[0]["address"] == "google_compute_firewall.allow_internal"
    assert drifted[0]["changed_attributes"] == ["source_ranges"]


def test_parse_drifted_resources_returns_empty_for_no_drift() -> None:
    assert _parse_drifted_resources(SAMPLE_NO_DRIFT_PLAN) == []


def test_build_drift_report_no_drift() -> None:
    report = build_drift_report("my-workspace", [])

    assert "No drift detected" in report
    assert "my-workspace" in report


def test_build_drift_report_lists_drifted_resources() -> None:
    drifted = _parse_drifted_resources(SAMPLE_REFRESH_ONLY_PLAN)
    report = build_drift_report("my-workspace", drifted)

    assert "1 resource(s) have changed outside Terraform" in report
    assert "google_compute_firewall.allow_internal" in report
    assert "source_ranges" in report


def test_detect_drift_rejects_missing_workspace() -> None:
    result = detect_infrastructure_drift("this-workspace-does-not-exist")

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_detect_drift_reports_no_drift(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "drift-test-workspace"
    workspace.mkdir()
    (workspace / "terraform.tfvars").write_text("project_id = \"test\"\n")

    monkeypatch.setattr(
        "terraform_agent.tools.drift_tools.get_workspace_path",
        lambda name: workspace,
    )

    def fake_run_terraform_command(workspace_name, arguments):
        if arguments[0] == "init":
            return {"status": "success", "return_code": 0}
        if arguments[0] == "plan":
            return {"status": "success", "return_code": 0}
        if arguments[0] == "show":
            return {
                "status": "success",
                "stdout": json.dumps(SAMPLE_NO_DRIFT_PLAN),
            }
        raise AssertionError(f"Unexpected command: {arguments}")

    with patch(
        "terraform_agent.tools.drift_tools._run_terraform_command",
        side_effect=fake_run_terraform_command,
    ):
        result = detect_infrastructure_drift("drift-test-workspace")

    assert result["status"] == "success"
    assert result["drift_detected"] is False
    assert result["drifted_resource_count"] == 0


def test_detect_drift_reports_real_drift(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "drift-test-workspace-2"
    workspace.mkdir()
    (workspace / "terraform.tfvars").write_text("project_id = \"test\"\n")

    monkeypatch.setattr(
        "terraform_agent.tools.drift_tools.get_workspace_path",
        lambda name: workspace,
    )

    def fake_run_terraform_command(workspace_name, arguments):
        if arguments[0] == "init":
            return {"status": "success", "return_code": 0}
        if arguments[0] == "plan":
            # -detailed-exitcode: 2 means drift detected. A raw
            # `terraform plan` exit code of 2 is not itself a shell
            # failure, so status stays "error" only for genuine
            # failures (return_code not in (0, 2)), which this test
            # exercises via the return_code field directly.
            return {"status": "error", "return_code": 2}
        if arguments[0] == "show":
            return {
                "status": "success",
                "stdout": json.dumps(SAMPLE_REFRESH_ONLY_PLAN),
            }
        raise AssertionError(f"Unexpected command: {arguments}")

    with patch(
        "terraform_agent.tools.drift_tools._run_terraform_command",
        side_effect=fake_run_terraform_command,
    ):
        result = detect_infrastructure_drift("drift-test-workspace-2")

    assert result["status"] == "success"
    assert result["drift_detected"] is True
    assert result["drifted_resource_count"] == 1
    assert (
        result["drifted_resources"][0]["address"]
        == "google_compute_firewall.allow_internal"
    )

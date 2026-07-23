"""Unit tests for the bounded cost estimation tool."""

from __future__ import annotations

from terraform_agent.tools.cost_tools import (
    estimate_cloud_sql_monthly_cost,
    estimate_compute_engine_monthly_cost,
    estimate_gke_control_plane_monthly_cost,
    estimate_workspace_cost,
    parse_cloud_sql_custom_tier,
)


def test_parse_cloud_sql_custom_tier_extracts_vcpu_and_memory() -> None:
    assert parse_cloud_sql_custom_tier("db-custom-2-7680") == (2, 7680)
    assert parse_cloud_sql_custom_tier("db-custom-4-15360") == (4, 15360)


def test_parse_cloud_sql_custom_tier_returns_none_for_shared_core() -> None:
    assert parse_cloud_sql_custom_tier("db-f1-micro") is None
    assert parse_cloud_sql_custom_tier("db-g1-small") is None


def test_parse_cloud_sql_custom_tier_returns_none_for_unrecognized() -> None:
    assert parse_cloud_sql_custom_tier("not-a-real-tier") is None


def test_estimate_cloud_sql_cost_zonal_custom_tier() -> None:
    result = estimate_cloud_sql_monthly_cost(
        "db-custom-2-7680", "ZONAL"
    )

    assert result["status"] == "estimated"
    # 2 vCPU * 0.0413 + 7.5 GB * 0.0070 = 0.1351/hr * 730 ~= $98.62
    assert 95.0 < result["monthly_cost_usd"] < 102.0


def test_estimate_cloud_sql_cost_regional_roughly_doubles_zonal() -> None:
    zonal = estimate_cloud_sql_monthly_cost("db-custom-2-7680", "ZONAL")
    regional = estimate_cloud_sql_monthly_cost(
        "db-custom-2-7680", "REGIONAL"
    )

    # Compare the ratio directly rather than round(zonal * 2, 2), since
    # rounding zonal first and then multiplying loses precision versus
    # the implementation's own multiply-then-round-once order.
    ratio = regional["monthly_cost_usd"] / zonal["monthly_cost_usd"]
    assert 1.99 < ratio < 2.01


def test_estimate_cloud_sql_cost_shared_core_flat_rate() -> None:
    result = estimate_cloud_sql_monthly_cost("db-f1-micro")

    assert result["status"] == "estimated"
    assert result["monthly_cost_usd"] == 8.00


def test_estimate_cloud_sql_cost_unknown_tier() -> None:
    result = estimate_cloud_sql_monthly_cost("db-perf-optimized-N-2")

    assert result["status"] == "unknown_tier"
    assert result["monthly_cost_usd"] is None


def test_estimate_compute_engine_cost_known_machine_type() -> None:
    result = estimate_compute_engine_monthly_cost("e2-standard-4")

    assert result["status"] == "estimated"
    # Cited: e2-standard-4 ~= $97.84/month in us-central1.
    assert 95.0 < result["monthly_cost_usd"] < 100.0


def test_estimate_compute_engine_cost_scales_with_instance_count() -> None:
    one = estimate_compute_engine_monthly_cost("e2-medium", instance_count=1)
    three = estimate_compute_engine_monthly_cost(
        "e2-medium", instance_count=3
    )

    ratio = three["monthly_cost_usd"] / one["monthly_cost_usd"]
    assert 2.99 < ratio < 3.01


def test_estimate_compute_engine_cost_unknown_machine_type() -> None:
    result = estimate_compute_engine_monthly_cost("n2-standard-96")

    assert result["status"] == "unknown_machine_type"
    assert result["monthly_cost_usd"] is None


def test_estimate_gke_control_plane_cost() -> None:
    result = estimate_gke_control_plane_monthly_cost()

    assert result["status"] == "estimated"
    # 0.10/hr * 730 = $73.00
    assert result["monthly_cost_usd"] == 73.00


def test_estimate_workspace_cost_rejects_missing_workspace() -> None:
    result = estimate_workspace_cost("this-workspace-does-not-exist")

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_estimate_workspace_cost_rejects_missing_var_file(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "cost-test-workspace"
    workspace.mkdir()

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-workspace")

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_estimate_workspace_cost_detects_cloud_sql(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "cost-test-cloudsql"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'tier = "db-custom-2-7680"\n'
        'availability_type = "REGIONAL"\n'
    )

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-cloudsql")

    assert result["status"] == "success"
    assert result["estimated_monthly_cost_usd"] > 0
    assert len(result["line_items"]) == 1
    assert result["line_items"][0]["status"] == "estimated"


def test_estimate_workspace_cost_detects_gke_standard(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "cost-test-gke"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'cluster_mode = "STANDARD"\n'
        'node_machine_type = "e2-standard-4"\n'
        "node_min_count = 2\n"
        "node_max_count = 5\n"
    )

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-gke")

    assert result["status"] == "success"
    # Node pool line item + control plane fee.
    assert len(result["line_items"]) == 2
    node_item = result["line_items"][0]
    assert "2x e2-standard-4" in node_item["resource"]


def test_estimate_workspace_cost_flags_autopilot_as_not_estimable(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "cost-test-autopilot"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'cluster_mode = "AUTOPILOT"\n'
    )

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-autopilot")

    assert result["status"] == "success"
    assert result["line_items"] == []
    assert any(
        "Autopilot" in note for note in result["not_estimated"]
    )


def test_estimate_workspace_cost_flags_usage_based_services(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "cost-test-cloudrun"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'service_name = "my-app"\n'
        'container_image = "gcr.io/my-project/my-app:latest"\n'
    )

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-cloudrun")

    assert result["status"] == "success"
    assert result["estimated_monthly_cost_usd"] == 0
    assert result["line_items"] == []
    assert any("Cloud Run" in note for note in result["not_estimated"])


def test_estimate_workspace_cost_supports_assembler_prefixed_keys(
    tmp_path, monkeypatch
) -> None:
    """The composed Cloud Run + Cloud SQL assembler uses db_tier /
    db_availability_type rather than the standalone generator's tier /
    availability_type -- both must be detected."""

    workspace = tmp_path / "cost-test-assembler"
    workspace.mkdir()
    (workspace / "terraform.tfvars.example").write_text(
        'db_tier = "db-custom-2-7680"\n'
        'db_availability_type = "REGIONAL"\n'
    )

    monkeypatch.setattr(
        "terraform_agent.tools.cost_tools.get_workspace_path",
        lambda name: workspace,
    )

    result = estimate_workspace_cost("cost-test-assembler")

    assert result["status"] == "success"
    assert len(result["line_items"]) == 1
    assert result["line_items"][0]["status"] == "estimated"

"""Offline end-to-end tests for the generated Cloud SQL Terraform workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloudsql-e2e-test"

SQL_INSTANCE_ADDRESS = "google_sql_database_instance.this"
SQL_DATABASE_ADDRESS = "google_sql_database.application"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "database.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
    "validation-report.md",
}


@pytest.fixture(scope="session")
def repository_root() -> Path:
    """Return the repository root directory."""

    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def cloudsql_workspace(repository_root: Path) -> Path:
    """Return the generated Cloud SQL workspace."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated Cloud SQL workspace does not exist: {workspace}\n"
            "Generate the cloudsql-e2e-test workspace before running this test."
        )

    if not workspace.is_dir():
        pytest.fail(f"Cloud SQL workspace path is not a directory: {workspace}")

    return workspace


@pytest.fixture(scope="session")
def terraform_runner(cloudsql_workspace: Path) -> TerraformRunner:
    """Create a Terraform command runner for the Cloud SQL workspace."""

    return TerraformRunner(cloudsql_workspace)


@pytest.fixture(scope="session")
def terraform_variables() -> dict[str, Any]:
    """Return deterministic variables for the offline Terraform plan."""

    return {
        "project_id": "test-project",
        "region": "asia-south1",
        "instance_name": "cloudsql-e2e-test",
        "private_network": (
            "projects/test-project/global/networks/test-vpc"
        ),
        "database_version": "POSTGRES_16",
        "tier": "db-custom-2-7680",
        "availability_type": "REGIONAL",
        "disk_size_gb": 100,
        "database_name": "application",
        "enable_iam_database_authentication": True,
        "backup_start_time": "02:00",
        "backup_retained_count": 14,
        "transaction_log_retention_days": 7,
        "maintenance_day": 7,
        "maintenance_hour": 3,
        "deletion_protection": True,
        "environment": "test",
        "owner": "platform-team",
        "application": "terraform-adk-agent",
    }


@pytest.fixture(scope="session")
def terraform_plan_path(cloudsql_workspace: Path) -> Path:
    """Return the Terraform plan output path."""

    return cloudsql_workspace / "cloudsql-e2e.tfplan"


@pytest.fixture(scope="session")
def terraform_plan(
    terraform_runner: TerraformRunner,
    terraform_variables: dict[str, Any],
    terraform_plan_path: Path,
) -> dict[str, Any]:
    """Create and return the Terraform plan result."""

    result = terraform_runner.plan(
        variables=terraform_variables,
        plan_file="cloudsql-e2e.tfplan",
    )
    

    assert result.command_result.return_code in (0, 2), (
        "Terraform plan failed.\n"
        f"STDOUT:\n{result.command_result.stdout}\n"
        f"STDERR:\n{result.command_result.stderr}"

    )

    return {
        "result": result,
        "plan_path": result.plan_file,
    }


@pytest.fixture(scope="session")
def terraform_plan_json(
    terraform_runner: TerraformRunner,
    terraform_plan: dict[str, Any],
) -> dict[str, Any]:
    """Return the Terraform plan as JSON."""

    return terraform_runner.show_json(
        plan_file=terraform_plan["plan_path"],
    )



def _planned_resources(plan_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return planned root-module resources indexed by Terraform address."""

    root_module = plan_json.get("planned_values", {}).get("root_module", {})
    resources = root_module.get("resources", [])

    return {
        resource["address"]: resource
        for resource in resources
        if "address" in resource
    }


def test_expected_cloudsql_files_exist(cloudsql_workspace: Path) -> None:
    """Verify that all expected Cloud SQL files were generated."""

    generated_files = {
        path.name
        for path in cloudsql_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - generated_files

    assert not missing_files, (
        "The generated Cloud SQL workspace is missing files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    cloudsql_workspace: Path,
) -> None:
    """Verify important Cloud SQL values and secure defaults."""

    main_tf = (cloudsql_workspace / "main.tf").read_text(encoding="utf-8")
    database_tf = (
        cloudsql_workspace / "database.tf"
    ).read_text(encoding="utf-8")

    assert 'resource "google_sql_database_instance" "this"' in main_tf
    assert 'resource "google_sql_database" "application"' in database_tf

    assert "ipv4_enabled" in main_tf
    assert "= false" in main_tf
    assert "private_network" in main_tf
    assert "var.private_network" in main_tf
    assert "deletion_protection = var.deletion_protection" in main_tf

    assert "backup_configuration" in main_tf
    assert "point_in_time_recovery_enabled" in main_tf
    assert "transaction_log_retention_days" in main_tf
    assert "retained_backups" in main_tf
    assert "maintenance_window" in main_tf

    assert "password" not in main_tf.lower()
    assert "password" not in database_tf.lower()


def test_terraform_formatting(terraform_runner: TerraformRunner) -> None:
    """Verify that the generated Terraform is correctly formatted."""

    result = terraform_runner.fmt(check=True)

    assert result.return_code == 0, (
        "terraform fmt check failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def test_terraform_initialization(terraform_runner: TerraformRunner) -> None:
    """Verify that Terraform initializes without a backend."""

    result = terraform_runner.init()

    assert result.return_code == 0, (
        "terraform init failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def test_terraform_validation(terraform_runner: TerraformRunner) -> None:
    """Verify that the generated Terraform configuration is valid."""

    result = terraform_runner.validate()

    assert result.return_code == 0, (
        "terraform validate failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def test_terraform_plan(terraform_plan: dict[str, Any]) -> None:
    """Verify that Terraform creates an offline Cloud SQL plan."""

    result = terraform_plan["result"]

    assert result.command_result.return_code in (0, 2)
    assert result.plan_file is not None
    assert terraform_plan["plan_path"].exists()


def test_plan_contains_expected_cloudsql_resources(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the Cloud SQL instance and database exist in the plan."""

    resources = _planned_resources(terraform_plan_json)

    assert SQL_INSTANCE_ADDRESS in resources
    assert SQL_DATABASE_ADDRESS in resources

    assert resources[SQL_INSTANCE_ADDRESS]["type"] == (
        "google_sql_database_instance"
    )
    assert resources[SQL_DATABASE_ADDRESS]["type"] == "google_sql_database"


def test_plan_uses_private_ip_only(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the planned Cloud SQL instance does not expose public IPv4."""

    resources = _planned_resources(terraform_plan_json)
    instance = resources[SQL_INSTANCE_ADDRESS]["values"]

    ip_configuration = instance["settings"][0]["ip_configuration"][0]

    assert ip_configuration["ipv4_enabled"] is False
    assert ip_configuration["private_network"] == (
        "projects/test-project/global/networks/test-vpc"
    )


def test_plan_enables_backup_and_pitr(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify backup retention and point-in-time recovery settings."""

    resources = _planned_resources(terraform_plan_json)
    instance = resources[SQL_INSTANCE_ADDRESS]["values"]

    backup = instance["settings"][0]["backup_configuration"][0]

    assert backup["enabled"] is True
    assert backup["point_in_time_recovery_enabled"] is True
    assert backup["transaction_log_retention_days"] == 7
    assert backup["start_time"] == "02:00"

    retained_backups = backup["backup_retention_settings"][0]
    assert retained_backups["retained_backups"] == 14


def test_plan_uses_secure_instance_defaults(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify high availability and deletion protection defaults."""

    resources = _planned_resources(terraform_plan_json)
    instance = resources[SQL_INSTANCE_ADDRESS]["values"]

    assert instance["database_version"] == "POSTGRES_16"
    assert instance["deletion_protection"] is True
    assert instance["settings"][0]["availability_type"] == "REGIONAL"
    assert instance["settings"][0]["tier"] == "db-custom-2-7680"


def test_export_cloudsql_plan_summary(
    cloudsql_workspace: Path,
    terraform_plan_json: dict[str, Any],
) -> None:
    """Export a compact Cloud SQL plan summary for diagnostics."""

    resources = _planned_resources(terraform_plan_json)

    summary = {
        "workspace": WORKSPACE_NAME,
        "resource_count": len(resources),
        "resource_addresses": sorted(resources),
        "cloud_sql_instance_present": SQL_INSTANCE_ADDRESS in resources,
        "database_present": SQL_DATABASE_ADDRESS in resources,
        "deployment_performed": False,
    }

    summary_path = cloudsql_workspace / "cloudsql-plan-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    assert summary_path.exists()
    assert summary["cloud_sql_instance_present"] is True
    assert summary["database_present"] is True
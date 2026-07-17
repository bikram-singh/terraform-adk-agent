"""Safe end-to-end tests for a generated GCS Terraform project.

These tests execute real Terraform commands but do not create or destroy
Google Cloud resources.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "gcs-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
    "validation-report.md",
}


@pytest.fixture(scope="module")
def gcs_workspace(repository_root: Path) -> Path:
    """Return the generated GCS workspace and verify that it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated GCS workspace does not exist: {workspace}\n"
            "Generate the gcs-e2e-test workspace before running this test."
        )

    if not workspace.is_dir():
        pytest.fail(f"GCS workspace path is not a directory: {workspace}")

    return workspace


@pytest.fixture(scope="module")
def gcs_var_file(gcs_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when necessary."""

    example_file = gcs_workspace / "terraform.tfvars.example"
    variable_file = gcs_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def gcs_runner(
    gcs_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the GCS workspace."""

    return terraform_runner_factory(gcs_workspace)


def test_expected_gcs_files_exist(gcs_workspace: Path) -> None:
    """Verify that the GCS generator produced every required file."""

    existing_files = {
        path.name
        for path in gcs_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        "The generated GCS workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_gcs_configuration_contains_expected_values(
    gcs_workspace: Path,
    gcs_var_file: Path,
) -> None:
    """Verify important values produced by the GCS generator."""

    main_content = (gcs_workspace / "main.tf").read_text(encoding="utf-8")
    variable_content = gcs_var_file.read_text(encoding="utf-8")

    assert 'resource "google_storage_bucket" "this"' in main_content
    assert "uniform_bucket_level_access = true" in main_content
    assert 'public_access_prevention    = "enforced"' in main_content
    assert "versioning" in main_content
    assert "enabled = true" in main_content

    assert "project_id" in variable_content
    assert "dhg-vaccine-rateauto-nonpord" in variable_content

    assert "bucket_name" in variable_content
    assert "dhg-vaccine-rateauto-gcs-e2e-test" in variable_content

    assert "location" in variable_content
    assert "asia-south1" in variable_content

    assert "storage_class" in variable_content
    assert "STANDARD" in variable_content


def test_terraform_formatting(gcs_runner: TerraformRunner) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = gcs_runner.fmt()
    assert format_result.succeeded

    format_check_result = gcs_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(gcs_runner: TerraformRunner) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = gcs_runner.init(backend=False)

    assert result.succeeded
    assert "Terraform has been successfully initialized" in result.combined_output


def test_terraform_validation(gcs_runner: TerraformRunner) -> None:
    """Validate the generated Terraform configuration."""

    result = gcs_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    gcs_runner: TerraformRunner,
    gcs_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan."""

    plan_result = gcs_runner.plan(
        var_file=gcs_var_file,
        plan_file="gcs-e2e.tfplan",
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = gcs_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    bucket_changes = [
        resource
        for resource in resource_changes
        if resource.get("address") == "google_storage_bucket.this"
    ]

    assert len(bucket_changes) == 1

    bucket_change = bucket_changes[0]
    actions = bucket_change.get("change", {}).get("actions", [])

    assert actions == ["create"]

    planned_values = (
        plan_json
        .get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    bucket_resources = [
        resource
        for resource in planned_values
        if resource.get("address") == "google_storage_bucket.this"
    ]

    assert len(bucket_resources) == 1

    bucket_values = bucket_resources[0].get("values", {})

    assert bucket_values["project"] == "dhg-vaccine-rateauto-nonpord"
    assert bucket_values["name"] == "dhg-vaccine-rateauto-gcs-e2e-test"
    assert bucket_values["location"] == "ASIA-SOUTH1"
    assert bucket_values["storage_class"] == "STANDARD"
    assert bucket_values["uniform_bucket_level_access"] is True
    assert bucket_values["public_access_prevention"] == "enforced"

    versioning = bucket_values.get("versioning", [])
    assert versioning
    assert versioning[0]["enabled"] is True


def test_plan_contains_only_expected_resource(
    gcs_runner: TerraformRunner,
) -> None:
    """Ensure that the generated plan contains no unexpected resources."""

    plan_file = gcs_runner.working_directory / "gcs-e2e.tfplan"

    assert plan_file.exists()

    plan_json = gcs_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert resource_addresses == {"google_storage_bucket.this"}


def test_export_plan_summary(
    gcs_runner: TerraformRunner,
) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = gcs_runner.working_directory / "gcs-e2e.tfplan"
    summary_file = gcs_runner.working_directory / "gcs-e2e-plan-summary.json"

    plan_json = gcs_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    summary = {
        "workspace": WORKSPACE_NAME,
        "terraform_version": plan_json.get("terraform_version"),
        "format_version": plan_json.get("format_version"),
        "resource_changes": [
            {
                "address": resource.get("address"),
                "type": resource.get("type"),
                "name": resource.get("name"),
                "actions": resource.get("change", {}).get("actions", []),
            }
            for resource in resource_changes
        ],
    }

    summary_file.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    assert summary_file.exists()
    assert summary_file.stat().st_size > 0

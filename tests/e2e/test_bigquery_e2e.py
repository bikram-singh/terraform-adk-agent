"""Safe end-to-end tests for a generated BigQuery Terraform project.

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


WORKSPACE_NAME = "bigquery-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "tables.tf",
    "iam.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_RESOURCE_ADDRESSES = {
    "google_bigquery_dataset.this",
    'google_bigquery_table.this["events"]',
}


@pytest.fixture(scope="module")
def bigquery_workspace(repository_root: Path) -> Path:
    """Return the generated BigQuery workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated BigQuery workspace does not exist: {workspace}\n"
            "Generate the bigquery-e2e-test workspace before running this test."
        )

    if not workspace.is_dir():
        pytest.fail(
            f"BigQuery workspace path is not a directory: {workspace}"
        )

    return workspace


@pytest.fixture(scope="module")
def bigquery_var_file(bigquery_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = bigquery_workspace / "terraform.tfvars.example"
    variable_file = bigquery_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def bigquery_runner(
    bigquery_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the BigQuery workspace."""

    return terraform_runner_factory(bigquery_workspace)


def test_expected_bigquery_files_exist(
    bigquery_workspace: Path,
) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name
        for path in bigquery_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        "The generated BigQuery workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    bigquery_workspace: Path,
    bigquery_var_file: Path,
) -> None:
    """Verify important security and dataset configuration values."""

    main_content = (
        bigquery_workspace / "main.tf"
    ).read_text(encoding="utf-8")

    tables_content = (
        bigquery_workspace / "tables.tf"
    ).read_text(encoding="utf-8")

    iam_content = (
        bigquery_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    variables_content = bigquery_var_file.read_text(encoding="utf-8")

    assert 'resource "google_bigquery_dataset" "this"' in main_content
    assert "delete_contents_on_destroy" in main_content
    assert "= false" in main_content
    assert "labels" in main_content
    assert "= local.common_labels" in main_content

    assert 'resource "google_bigquery_table" "this"' in tables_content
    assert "deletion_protection" in tables_content
    assert "var.deletion_protection" in tables_content
    assert "for_each = var.tables" in tables_content

    assert 'resource "google_bigquery_dataset_iam_member" "readers"' in iam_content
    assert 'resource "google_bigquery_dataset_iam_member" "editors"' in iam_content
    assert 'role       = "roles/bigquery.dataViewer"' in iam_content
    assert 'role       = "roles/bigquery.dataEditor"' in iam_content

    assert 'project_id = "your-project-id"' in variables_content
    assert "deletion_protection          = true" in variables_content
    assert "reader_members = []" in variables_content
    assert "editor_members = []" in variables_content


def test_terraform_formatting(
    bigquery_runner: TerraformRunner,
) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = bigquery_runner.fmt()
    assert format_result.succeeded

    format_check_result = bigquery_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(
    bigquery_runner: TerraformRunner,
) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = bigquery_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized"
        in result.combined_output
    )


def test_terraform_validation(
    bigquery_runner: TerraformRunner,
) -> None:
    """Validate the generated Terraform configuration."""

    result = bigquery_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    bigquery_runner: TerraformRunner,
    bigquery_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan."""

    plan_result = bigquery_runner.plan(
        var_file=bigquery_var_file,
        plan_file="bigquery-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = bigquery_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address")
        for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

    dataset_changes = [
        resource
        for resource in resource_changes
        if resource.get("address") == "google_bigquery_dataset.this"
    ]

    assert len(dataset_changes) == 1

    actions = (
        dataset_changes[0]
        .get("change", {})
        .get("actions", [])
    )

    assert actions == ["create"]

    planned_resources = (
        plan_json
        .get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    dataset_resources = [
        resource
        for resource in planned_resources
        if resource.get("address") == "google_bigquery_dataset.this"
    ]

    assert len(dataset_resources) == 1

    dataset_values = dataset_resources[0].get("values", {})

    assert dataset_values.get("dataset_id") == "analytics"
    assert dataset_values.get("delete_contents_on_destroy") is False


def test_plan_contains_no_dataset_iam_bindings_by_default(
    bigquery_runner: TerraformRunner,
) -> None:
    """Ensure no reader/editor IAM bindings are planned without members."""

    plan_file = (
        bigquery_runner.working_directory
        / "bigquery-e2e.tfplan"
    )

    assert plan_file.exists()

    plan_json = bigquery_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert not any(
        address.startswith("google_bigquery_dataset_iam_member.")
        for address in resource_addresses
    )


def test_export_bigquery_plan_summary(
    bigquery_runner: TerraformRunner,
) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = (
        bigquery_runner.working_directory
        / "bigquery-e2e.tfplan"
    )

    summary_file = (
        bigquery_runner.working_directory
        / "bigquery-e2e-plan-summary.json"
    )

    plan_json = bigquery_runner.show_json(plan_file=plan_file)

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
                "actions": (
                    resource
                    .get("change", {})
                    .get("actions", [])
                ),
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
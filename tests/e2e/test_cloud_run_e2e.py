"""Safe end-to-end tests for a generated Cloud Run Terraform project.

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


WORKSPACE_NAME = "cloudrun-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "iam.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_RESOURCE_ADDRESSES = {
    "google_service_account.runtime",
    "google_cloud_run_v2_service.this",
}


@pytest.fixture(scope="module")
def cloudrun_workspace(repository_root: Path) -> Path:
    """Return the generated Cloud Run workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated Cloud Run workspace does not exist: {workspace}\n"
            "Generate the cloudrun-e2e-test workspace before running this test."
        )

    if not workspace.is_dir():
        pytest.fail(
            f"Cloud Run workspace path is not a directory: {workspace}"
        )

    return workspace


@pytest.fixture(scope="module")
def cloudrun_var_file(cloudrun_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = cloudrun_workspace / "terraform.tfvars.example"
    variable_file = cloudrun_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def cloudrun_runner(
    cloudrun_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the Cloud Run workspace."""

    return terraform_runner_factory(cloudrun_workspace)


def test_expected_cloudrun_files_exist(
    cloudrun_workspace: Path,
) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name
        for path in cloudrun_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        "The generated Cloud Run workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    cloudrun_workspace: Path,
    cloudrun_var_file: Path,
) -> None:
    """Verify important security and runtime configuration values."""

    main_content = (
        cloudrun_workspace / "main.tf"
    ).read_text(encoding="utf-8")

    iam_content = (
        cloudrun_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    variables_content = cloudrun_var_file.read_text(encoding="utf-8")

    assert 'resource "google_cloud_run_v2_service" "this"' in main_content
    assert "deletion_protection = var.deletion_protection" in main_content
    assert "service_account = google_service_account.runtime.email" in main_content
    assert "min_instance_count = var.min_instances" in main_content
    assert "max_instance_count = var.max_instances" in main_content
    assert "secret_key_ref" in main_content
    assert 'mount_path = "/cloudsql"' in main_content
    assert 'managed_by  = "terraform"' in main_content

    assert 'resource "google_service_account" "runtime"' in iam_content
    assert 'role     = "roles/run.invoker"' in iam_content
    assert 'member   = "allUsers"' in iam_content
    assert "count    = var.allow_unauthenticated ? 1 : 0" in iam_content

    assert 'project_id      = "your-project-id"' in variables_content
    assert 'region          = "asia-south1"' in variables_content
    assert "allow_unauthenticated = false" in variables_content
    assert "deletion_protection   = true" in variables_content


def test_terraform_formatting(
    cloudrun_runner: TerraformRunner,
) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = cloudrun_runner.fmt()
    assert format_result.succeeded

    format_check_result = cloudrun_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(
    cloudrun_runner: TerraformRunner,
) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = cloudrun_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized"
        in result.combined_output
    )


def test_terraform_validation(
    cloudrun_runner: TerraformRunner,
) -> None:
    """Validate the generated Terraform configuration."""

    result = cloudrun_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    cloudrun_runner: TerraformRunner,
    cloudrun_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan."""

    plan_result = cloudrun_runner.plan(
        var_file=cloudrun_var_file,
        plan_file="cloudrun-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = cloudrun_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address")
        for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

    service_changes = [
        resource
        for resource in resource_changes
        if resource.get("address")
        == "google_cloud_run_v2_service.this"
    ]

    assert len(service_changes) == 1

    actions = (
        service_changes[0]
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

    service_resources = [
        resource
        for resource in planned_resources
        if resource.get("address")
        == "google_cloud_run_v2_service.this"
    ]

    assert len(service_resources) == 1

    service_values = service_resources[0].get("values", {})

    assert service_values.get("location") == "asia-south1"
    assert service_values.get("deletion_protection") is True
    assert (
        service_values.get("ingress")
        == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    )


def test_plan_contains_no_public_invoker_by_default(
    cloudrun_runner: TerraformRunner,
) -> None:
    """Ensure public Cloud Run invocation is absent by default."""

    plan_file = (
        cloudrun_runner.working_directory
        / "cloudrun-e2e.tfplan"
    )

    assert plan_file.exists()

    plan_json = cloudrun_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert (
        "google_cloud_run_v2_service_iam_member.public_invoker[0]"
        not in resource_addresses
    )


def test_export_cloudrun_plan_summary(
    cloudrun_runner: TerraformRunner,
) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = (
        cloudrun_runner.working_directory
        / "cloudrun-e2e.tfplan"
    )

    summary_file = (
        cloudrun_runner.working_directory
        / "cloudrun-e2e-plan-summary.json"
    )

    plan_json = cloudrun_runner.show_json(plan_file=plan_file)

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

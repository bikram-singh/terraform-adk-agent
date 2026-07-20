"""Safe end-to-end tests for a generated Cloud Functions Terraform project.

These tests execute real Terraform commands but do not create or destroy
Google Cloud resources.

Unlike the other generators, Cloud Functions references a local source
archive path (`var.source_archive_path`) through Terraform's `filesha256()`
function, which is evaluated during `plan` -- not just `apply`. A zero-byte
or missing file will fail `terraform plan` even though no cloud resources
are touched. This suite creates a minimal real zip archive on disk before
planning, mirroring what a developer would do locally before running
Terraform for a real deployment.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloud-functions-e2e-test"

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
    "google_storage_bucket.source",
    "google_storage_bucket_object.source_archive",
    "google_service_account.runtime",
    "google_cloudfunctions2_function.this",
}


@pytest.fixture(scope="module")
def cloud_functions_workspace(repository_root: Path) -> Path:
    """Return the generated Cloud Functions workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated Cloud Functions workspace does not exist: {workspace}\n"
            "Generate the cloud-functions-e2e-test workspace before running "
            "this test."
        )

    if not workspace.is_dir():
        pytest.fail(
            f"Cloud Functions workspace path is not a directory: {workspace}"
        )

    return workspace


@pytest.fixture(scope="module")
def cloud_functions_source_archive(
    cloud_functions_workspace: Path,
) -> Path:
    """Create a minimal real zip archive at the default source_archive_path.

    `filesha256(var.source_archive_path)` is evaluated during `terraform
    plan`, so this file must exist on disk and be a valid zip before
    planning, not just before apply.
    """

    archive_path = cloud_functions_workspace / "dist" / "function-source.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "main.py",
            "def main(request):\n    return 'ok'\n",
        )

    return archive_path


@pytest.fixture(scope="module")
def cloud_functions_var_file(
    cloud_functions_workspace: Path,
    cloud_functions_source_archive: Path,
) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = cloud_functions_workspace / "terraform.tfvars.example"
    variable_file = cloud_functions_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def cloud_functions_runner(
    cloud_functions_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the Cloud Functions workspace."""

    return terraform_runner_factory(cloud_functions_workspace)


def test_expected_cloud_functions_files_exist(
    cloud_functions_workspace: Path,
) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name
        for path in cloud_functions_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        "The generated Cloud Functions workspace is missing required "
        f"files: {sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    cloud_functions_workspace: Path,
    cloud_functions_var_file: Path,
) -> None:
    """Verify important security and runtime configuration values."""

    main_content = (
        cloud_functions_workspace / "main.tf"
    ).read_text(encoding="utf-8")

    iam_content = (
        cloud_functions_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    variables_content = cloud_functions_var_file.read_text(encoding="utf-8")

    assert 'resource "google_storage_bucket" "source"' in main_content
    assert "uniform_bucket_level_access = true" in main_content
    assert 'public_access_prevention    = "enforced"' in main_content
    assert 'resource "google_storage_bucket_object" "source_archive"' in main_content
    assert "filesha256(var.source_archive_path)" in main_content
    assert 'resource "google_cloudfunctions2_function" "this"' in main_content
    assert "service_account_email" in main_content
    assert "google_service_account.runtime.email" in main_content

    assert 'resource "google_service_account" "runtime"' in iam_content
    assert 'resource "google_project_iam_member" "runtime_roles"' in iam_content
    assert 'resource "google_cloudfunctions2_function_iam_member" "public_invoker"' in iam_content
    assert "count          = var.allow_unauthenticated ? 1 : 0" in iam_content
    assert 'role           = "roles/cloudfunctions.invoker"' in iam_content
    assert 'member         = "allUsers"' in iam_content

    assert 'project_id = "your-project-id"' in variables_content
    assert 'region     = "asia-south1"' in variables_content
    assert 'ingress_settings      = "ALLOW_INTERNAL_ONLY"' in variables_content
    assert "allow_unauthenticated = false" in variables_content
    assert 'source_archive_path  = "./dist/function-source.zip"' in variables_content


def test_terraform_formatting(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = cloud_functions_runner.fmt()
    assert format_result.succeeded

    format_check_result = cloud_functions_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = cloud_functions_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized"
        in result.combined_output
    )


def test_terraform_validation(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Validate the generated Terraform configuration."""

    result = cloud_functions_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    cloud_functions_runner: TerraformRunner,
    cloud_functions_var_file: Path,
    cloud_functions_source_archive: Path,
) -> None:
    """Create and inspect a real Terraform execution plan."""

    plan_result = cloud_functions_runner.plan(
        var_file=cloud_functions_var_file,
        plan_file="cloud-functions-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = cloud_functions_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address")
        for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

    function_changes = [
        resource
        for resource in resource_changes
        if resource.get("address")
        == "google_cloudfunctions2_function.this"
    ]

    assert len(function_changes) == 1

    actions = (
        function_changes[0]
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

    function_resources = [
        resource
        for resource in planned_resources
        if resource.get("address")
        == "google_cloudfunctions2_function.this"
    ]

    assert len(function_resources) == 1

    function_values = function_resources[0].get("values", {})

    assert function_values.get("location") == "asia-south1"
    assert function_values.get("name") == "terraform-adk-function"


def test_plan_contains_no_public_invoker_by_default(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Ensure public Cloud Function invocation is absent by default."""

    plan_file = (
        cloud_functions_runner.working_directory
        / "cloud-functions-e2e.tfplan"
    )

    assert plan_file.exists()

    plan_json = cloud_functions_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert (
        "google_cloudfunctions2_function_iam_member.public_invoker[0]"
        not in resource_addresses
    )


def test_plan_contains_no_optional_iam_bindings_by_default(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Ensure no extra project/secret IAM bindings are planned by default."""

    plan_file = (
        cloud_functions_runner.working_directory
        / "cloud-functions-e2e.tfplan"
    )

    plan_json = cloud_functions_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert not any(
        address.startswith("google_project_iam_member.runtime_roles")
        for address in resource_addresses
    )
    assert not any(
        address.startswith(
            "google_secret_manager_secret_iam_member.secret_access"
        )
        for address in resource_addresses
    )


def test_export_cloud_functions_plan_summary(
    cloud_functions_runner: TerraformRunner,
) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = (
        cloud_functions_runner.working_directory
        / "cloud-functions-e2e.tfplan"
    )

    summary_file = (
        cloud_functions_runner.working_directory
        / "cloud-functions-e2e-plan-summary.json"
    )

    plan_json = cloud_functions_runner.show_json(plan_file=plan_file)

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

"""Safe end-to-end tests for a generated IAM Terraform project.

These tests execute real Terraform commands but do not create or destroy
Google Cloud resources.

Unlike the other generators, the IAM generator has no defaults for
`service_account_id` or `project_roles` -- both are required, and an empty
`project_roles` list raises a Python ValueError before any Terraform is even
rendered. The workspace fixture below must be generated with explicit
values (mirroring the unit test suite's fixture) rather than an empty
values dict.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "iam-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "project_iam.tf",
    "impersonation.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_RESOURCE_ADDRESSES = {
    "google_service_account.this",
    'google_project_iam_member.runtime_roles["roles/cloudsql.client"]',
    'google_project_iam_member.runtime_roles["roles/secretmanager.secretAccessor"]',
}


@pytest.fixture(scope="module")
def iam_workspace(repository_root: Path) -> Path:
    """Return the generated IAM workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated IAM workspace does not exist: {workspace}\n"
            "Generate the iam-e2e-test workspace (with an explicit "
            "service_account_id and project_roles) before running this "
            "test."
        )

    if not workspace.is_dir():
        pytest.fail(f"IAM workspace path is not a directory: {workspace}")

    return workspace


@pytest.fixture(scope="module")
def iam_var_file(iam_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = iam_workspace / "terraform.tfvars.example"
    variable_file = iam_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def iam_runner(
    iam_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the IAM workspace."""

    return terraform_runner_factory(iam_workspace)


def test_expected_iam_files_exist(iam_workspace: Path) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name for path in iam_workspace.iterdir() if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        f"The generated IAM workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    iam_workspace: Path,
    iam_var_file: Path,
) -> None:
    """Verify the dedicated service account and least-privilege bindings."""

    main_content = (iam_workspace / "main.tf").read_text(encoding="utf-8")

    project_iam_content = (
        iam_workspace / "project_iam.tf"
    ).read_text(encoding="utf-8")

    impersonation_content = (
        iam_workspace / "impersonation.tf"
    ).read_text(encoding="utf-8")

    variables_content = iam_var_file.read_text(encoding="utf-8")

    assert 'resource "google_service_account" "this"' in main_content
    assert "account_id   = var.service_account_id" in main_content

    assert 'resource "google_project_iam_member" "runtime_roles"' in project_iam_content
    assert "lifecycle" in project_iam_content
    assert "precondition" in project_iam_content
    assert (
        '!contains(["roles/owner", "roles/editor"], each.value)'
        in project_iam_content
    )

    assert (
        'resource "google_service_account_iam_member" "impersonators"'
        in impersonation_content
    )
    assert 'role                = "roles/iam.serviceAccountUser"' in impersonation_content
    assert "for_each = toset(var.impersonators)" in impersonation_content

    assert 'project_id = "your-project-id"' in variables_content
    assert 'service_account_id           = "app-runtime-sa"' in variables_content
    assert "roles/cloudsql.client" in variables_content
    assert "roles/secretmanager.secretAccessor" in variables_content
    assert "impersonators = []" in variables_content


def test_terraform_formatting(iam_runner: TerraformRunner) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = iam_runner.fmt()
    assert format_result.succeeded

    format_check_result = iam_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(iam_runner: TerraformRunner) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = iam_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized" in result.combined_output
    )


def test_terraform_validation(iam_runner: TerraformRunner) -> None:
    """Validate the generated Terraform configuration."""

    result = iam_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    iam_runner: TerraformRunner,
    iam_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan.

    This also exercises the lifecycle precondition on
    `google_project_iam_member.runtime_roles`: since both configured roles
    are known, static values (not owner/editor), Terraform evaluates the
    precondition during plan and the plan must still succeed.
    """

    plan_result = iam_runner.plan(
        var_file=iam_var_file,
        plan_file="iam-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = iam_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address") for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

    service_account_changes = [
        resource
        for resource in resource_changes
        if resource.get("address") == "google_service_account.this"
    ]

    assert len(service_account_changes) == 1

    actions = (
        service_account_changes[0].get("change", {}).get("actions", [])
    )

    assert actions == ["create"]

    planned_resources = (
        plan_json.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    service_account_resources = [
        resource
        for resource in planned_resources
        if resource.get("address") == "google_service_account.this"
    ]

    assert len(service_account_resources) == 1

    service_account_values = service_account_resources[0].get("values", {})

    assert service_account_values.get("account_id") == "app-runtime-sa"


def test_plan_contains_no_impersonation_bindings_by_default(
    iam_runner: TerraformRunner,
) -> None:
    """Ensure no impersonation bindings are planned without impersonators."""

    plan_file = iam_runner.working_directory / "iam-e2e.tfplan"

    assert plan_file.exists()

    plan_json = iam_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert not any(
        address.startswith("google_service_account_iam_member.impersonators")
        for address in resource_addresses
    )


def test_export_iam_plan_summary(iam_runner: TerraformRunner) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = iam_runner.working_directory / "iam-e2e.tfplan"

    summary_file = iam_runner.working_directory / "iam-e2e-plan-summary.json"

    plan_json = iam_runner.show_json(plan_file=plan_file)

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

    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    assert summary_file.exists()
    assert summary_file.stat().st_size > 0

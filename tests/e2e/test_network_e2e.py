"""Safe end-to-end tests for a generated Network (VPC) Terraform project.

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


WORKSPACE_NAME = "network-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "network.tf",
    "private_service_access.tf",
    "vpc_connector.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_RESOURCE_ADDRESSES = {
    "google_compute_network.this",
    "google_compute_subnetwork.this",
    "google_compute_global_address.private_service_range",
    "google_service_networking_connection.private_service_access",
    "google_vpc_access_connector.serverless[0]",
}


@pytest.fixture(scope="module")
def network_workspace(repository_root: Path) -> Path:
    """Return the generated Network workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated Network workspace does not exist: {workspace}\n"
            "Generate the network-e2e-test workspace before running this "
            "test."
        )

    if not workspace.is_dir():
        pytest.fail(
            f"Network workspace path is not a directory: {workspace}"
        )

    return workspace


@pytest.fixture(scope="module")
def network_var_file(network_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = network_workspace / "terraform.tfvars.example"
    variable_file = network_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def network_runner(
    network_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the Network workspace."""

    return terraform_runner_factory(network_workspace)


def test_expected_network_files_exist(network_workspace: Path) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name for path in network_workspace.iterdir() if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        f"The generated Network workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    network_workspace: Path,
    network_var_file: Path,
) -> None:
    """Verify important security and networking configuration values."""

    network_content = (
        network_workspace / "network.tf"
    ).read_text(encoding="utf-8")

    psa_content = (
        network_workspace / "private_service_access.tf"
    ).read_text(encoding="utf-8")

    connector_content = (
        network_workspace / "vpc_connector.tf"
    ).read_text(encoding="utf-8")

    variables_content = network_var_file.read_text(encoding="utf-8")

    assert 'resource "google_compute_network" "this"' in network_content
    assert "auto_create_subnetworks  = false" in network_content
    assert 'resource "google_compute_subnetwork" "this"' in network_content
    assert "private_ip_google_access = true" in network_content
    assert "dynamic \"secondary_ip_range\"" in network_content

    assert (
        'resource "google_compute_global_address" "private_service_range"'
        in psa_content
    )
    assert 'purpose       = "VPC_PEERING"' in psa_content
    assert (
        'resource "google_service_networking_connection" "private_service_access"'
        in psa_content
    )

    assert (
        'resource "google_vpc_access_connector" "serverless"' in connector_content
    )
    assert "count = var.enable_serverless_vpc_connector ? 1 : 0" in connector_content
    assert "lifecycle" in connector_content
    assert "precondition" in connector_content
    assert (
        "var.vpc_connector_max_instances > var.vpc_connector_min_instances"
        in connector_content
    )

    assert 'project_id   = "your-project-id"' in variables_content
    assert 'subnet_cidr  = "10.0.0.0/20"' in variables_content
    assert "secondary_ip_ranges = {}" in variables_content
    assert "enable_serverless_vpc_connector = true" in variables_content
    assert 'vpc_connector_cidr              = "10.10.0.0/28"' in variables_content


def test_terraform_formatting(network_runner: TerraformRunner) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = network_runner.fmt()
    assert format_result.succeeded

    format_check_result = network_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(network_runner: TerraformRunner) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = network_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized" in result.combined_output
    )


def test_terraform_validation(network_runner: TerraformRunner) -> None:
    """Validate the generated Terraform configuration."""

    result = network_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    network_runner: TerraformRunner,
    network_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan.

    This also exercises the lifecycle precondition on
    `google_vpc_access_connector.serverless` (max_instances >
    min_instances), since both are static, known values with the default
    tfvars (2 and 3 respectively).
    """

    plan_result = network_runner.plan(
        var_file=network_var_file,
        plan_file="network-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = network_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address") for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

    network_changes = [
        resource
        for resource in resource_changes
        if resource.get("address") == "google_compute_network.this"
    ]

    assert len(network_changes) == 1

    actions = network_changes[0].get("change", {}).get("actions", [])

    assert actions == ["create"]

    planned_resources = (
        plan_json.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    subnet_resources = [
        resource
        for resource in planned_resources
        if resource.get("address") == "google_compute_subnetwork.this"
    ]

    assert len(subnet_resources) == 1

    subnet_values = subnet_resources[0].get("values", {})

    assert subnet_values.get("ip_cidr_range") == "10.0.0.0/20"
    assert subnet_values.get("private_ip_google_access") is True


def test_plan_contains_no_secondary_ranges_by_default(
    network_runner: TerraformRunner,
) -> None:
    """Ensure the subnet plans with zero secondary IP ranges by default."""

    plan_file = network_runner.working_directory / "network-e2e.tfplan"

    assert plan_file.exists()

    plan_json = network_runner.show_json(plan_file=plan_file)

    planned_resources = (
        plan_json.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    subnet_resources = [
        resource
        for resource in planned_resources
        if resource.get("address") == "google_compute_subnetwork.this"
    ]

    assert len(subnet_resources) == 1

    secondary_ranges = subnet_resources[0].get("values", {}).get(
        "secondary_ip_range", []
    )

    assert secondary_ranges in (None, [])


def test_export_network_plan_summary(network_runner: TerraformRunner) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = network_runner.working_directory / "network-e2e.tfplan"

    summary_file = (
        network_runner.working_directory / "network-e2e-plan-summary.json"
    )

    plan_json = network_runner.show_json(plan_file=plan_file)

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

"""Safe end-to-end tests for a generated GKE Terraform project.

These tests execute real Terraform commands but do not create or destroy
Google Cloud resources.

The GKE generator produces both `google_container_cluster.standard` and
`google_container_cluster.autopilot` resources, gated by `count` on
`var.cluster_mode`. With the generator's default (`cluster_mode = "STANDARD"`)
only the Standard cluster, its node pool, and the node-role IAM bindings
should appear in the plan -- the Autopilot resource and its zero-count
sibling should not.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "gke-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "cluster.tf",
    "node_pool.tf",
    "iam.tf",
    "artifact_registry.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_RESOURCE_ADDRESSES = {
    "google_container_cluster.standard[0]",
    "google_container_node_pool.primary[0]",
    "google_service_account.nodes",
    "google_artifact_registry_repository.images[0]",
}

EXPECTED_NODE_ROLE_ADDRESSES = {
    'google_project_iam_member.node_roles["roles/logging.logWriter"]',
    'google_project_iam_member.node_roles["roles/monitoring.metricWriter"]',
    'google_project_iam_member.node_roles["roles/monitoring.viewer"]',
    'google_project_iam_member.node_roles["roles/stackdriver.resourceMetadata.writer"]',
    'google_project_iam_member.node_roles["roles/artifactregistry.reader"]',
}


@pytest.fixture(scope="module")
def gke_workspace(repository_root: Path) -> Path:
    """Return the generated GKE workspace and verify it exists."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated GKE workspace does not exist: {workspace}\n"
            "Generate the gke-e2e-test workspace before running this test."
        )

    if not workspace.is_dir():
        pytest.fail(f"GKE workspace path is not a directory: {workspace}")

    return workspace


@pytest.fixture(scope="module")
def gke_var_file(gke_workspace: Path) -> Path:
    """Create terraform.tfvars from the generated example when required."""

    example_file = gke_workspace / "terraform.tfvars.example"
    variable_file = gke_workspace / "terraform.tfvars"

    if not example_file.exists():
        pytest.fail(f"Missing generated variable example: {example_file}")

    if not variable_file.exists():
        shutil.copy2(example_file, variable_file)

    return variable_file


@pytest.fixture(scope="module")
def gke_runner(
    gke_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner configured for the GKE workspace."""

    return terraform_runner_factory(gke_workspace)


def test_expected_gke_files_exist(gke_workspace: Path) -> None:
    """Verify that the generator produced every required file."""

    existing_files = {
        path.name for path in gke_workspace.iterdir() if path.is_file()
    }

    missing_files = EXPECTED_FILES - existing_files

    assert not missing_files, (
        f"The generated GKE workspace is missing required files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_values(
    gke_workspace: Path,
    gke_var_file: Path,
) -> None:
    """Verify important security and cluster configuration values."""

    cluster_content = (
        gke_workspace / "cluster.tf"
    ).read_text(encoding="utf-8")

    node_pool_content = (
        gke_workspace / "node_pool.tf"
    ).read_text(encoding="utf-8")

    iam_content = (gke_workspace / "iam.tf").read_text(encoding="utf-8")

    variables_content = gke_var_file.read_text(encoding="utf-8")

    assert 'resource "google_container_cluster" "standard"' in cluster_content
    assert 'resource "google_container_cluster" "autopilot"' in cluster_content
    assert "count = local.is_standard ? 1 : 0" in cluster_content
    assert "count = local.is_autopilot ? 1 : 0" in cluster_content
    assert "enable_private_nodes    = true" in cluster_content
    assert "enable_shielded_nodes = true" in cluster_content
    assert "workload_identity_config" in cluster_content

    assert 'resource "google_container_node_pool" "primary"' in node_pool_content
    assert "count = local.is_standard ? 1 : 0" in node_pool_content
    assert "enable_secure_boot          = true" in node_pool_content
    assert "enable_integrity_monitoring = true" in node_pool_content

    assert 'resource "google_service_account" "nodes"' in iam_content
    assert "roles/logging.logWriter" in iam_content
    assert "roles/artifactregistry.reader" in iam_content

    assert 'cluster_mode = "STANDARD"' in variables_content
    assert "enable_private_endpoint = true" in variables_content
    assert "deletion_protection         = true" in variables_content
    assert "create_artifact_registry        = true" in variables_content
    assert "node_spot         = false" in variables_content


def test_terraform_formatting(gke_runner: TerraformRunner) -> None:
    """Format the generated Terraform project and verify formatting."""

    format_result = gke_runner.fmt()
    assert format_result.succeeded

    format_check_result = gke_runner.fmt(check=True)
    assert format_check_result.succeeded


def test_terraform_initialization(gke_runner: TerraformRunner) -> None:
    """Initialize Terraform without configuring a remote backend."""

    result = gke_runner.init(backend=False)

    assert result.succeeded
    assert (
        "Terraform has been successfully initialized" in result.combined_output
    )


def test_terraform_validation(gke_runner: TerraformRunner) -> None:
    """Validate the generated Terraform configuration."""

    result = gke_runner.validate()

    assert result.succeeded
    assert "The configuration is valid" in result.combined_output


def test_terraform_plan(
    gke_runner: TerraformRunner,
    gke_var_file: Path,
) -> None:
    """Create and inspect a real Terraform execution plan."""

    plan_result = gke_runner.plan(
        var_file=gke_var_file,
        plan_file="gke-e2e.tfplan",
        refresh=False,
    )

    assert plan_result.command_result.return_code in (0, 2)
    assert plan_result.has_changes is True

    plan_file = plan_result.plan_file

    assert plan_file is not None
    assert plan_file.exists()
    assert plan_file.stat().st_size > 0

    plan_json = gke_runner.show_json(plan_file=plan_file)

    resource_changes = plan_json.get("resource_changes", [])

    resource_addresses = {
        resource.get("address") for resource in resource_changes
    }

    assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)
    assert EXPECTED_NODE_ROLE_ADDRESSES.issubset(resource_addresses)

    cluster_changes = [
        resource
        for resource in resource_changes
        if resource.get("address") == "google_container_cluster.standard[0]"
    ]

    assert len(cluster_changes) == 1

    actions = cluster_changes[0].get("change", {}).get("actions", [])

    assert actions == ["create"]

    planned_resources = (
        plan_json.get("planned_values", {})
        .get("root_module", {})
        .get("resources", [])
    )

    cluster_resources = [
        resource
        for resource in planned_resources
        if resource.get("address") == "google_container_cluster.standard[0]"
    ]

    assert len(cluster_resources) == 1

    cluster_values = cluster_resources[0].get("values", {})

    assert cluster_values.get("name") == "platform-gke"
    assert cluster_values.get("location") == "asia-south1"
    assert cluster_values.get("enable_autopilot") in (None, False)


def test_plan_omits_autopilot_cluster_by_default(
    gke_runner: TerraformRunner,
) -> None:
    """Ensure the Autopilot cluster is absent when cluster_mode is STANDARD."""

    plan_file = gke_runner.working_directory / "gke-e2e.tfplan"

    assert plan_file.exists()

    plan_json = gke_runner.show_json(plan_file=plan_file)

    resource_addresses = {
        resource.get("address")
        for resource in plan_json.get("resource_changes", [])
    }

    assert "google_container_cluster.autopilot[0]" not in resource_addresses
    assert not any(
        address.startswith("google_container_cluster.autopilot")
        for address in resource_addresses
    )


def test_export_gke_plan_summary(gke_runner: TerraformRunner) -> None:
    """Write a readable JSON plan summary for troubleshooting."""

    plan_file = gke_runner.working_directory / "gke-e2e.tfplan"

    summary_file = (
        gke_runner.working_directory / "gke-e2e-plan-summary.json"
    )

    plan_json = gke_runner.show_json(plan_file=plan_file)

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

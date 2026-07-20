"""End-to-end tests for the generated Secret Manager Terraform workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.secret_manager.generator import (
    SecretManagerGenerator,
)
from tests.e2e.terraform_runner import TerraformRunner


WORKSPACE_NAME = "secret-manager-e2e-test"

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

EXPECTED_SECRETS = {
    "secret-manager-e2e-database-password",
    "secret-manager-e2e-api-token",
}

SECRET_RESOURCE_TYPE = "google_secret_manager_secret"
IAM_RESOURCE_TYPE = "google_secret_manager_secret_iam_member"

ACCESSOR_MEMBER = (
    "serviceAccount:runtime@test-project.iam.gserviceaccount.com"
)


@pytest.fixture(scope="session")
def repository_root() -> Path:
    """Return the repository root directory."""

    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def secret_manager_workspace(repository_root: Path) -> Path:
    """Generate and return the Secret Manager Terraform workspace."""

    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    generator = SecretManagerGenerator()
    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "secret_ids": sorted(EXPECTED_SECRETS),
                "replication_locations": [],
                "accessor_members": [ACCESSOR_MEMBER],
                "environment": "test",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
            },
        )
    )

    for filename, content in project.files.items():
        (workspace / filename).write_text(content, encoding="utf-8")

    return workspace


@pytest.fixture(scope="session")
def terraform_runner(
    secret_manager_workspace: Path,
) -> TerraformRunner:
    """Create a Terraform runner for the generated workspace."""

    return TerraformRunner(secret_manager_workspace)


@pytest.fixture(scope="session")
def terraform_variables() -> dict[str, Any]:
    """Return deterministic Terraform variables for plan validation."""

    return {
        "project_id": os.getenv(
            "SECRET_MANAGER_E2E_PROJECT_ID",
            "test-project",
        ),
        "region": "asia-south1",
        "secret_ids": sorted(EXPECTED_SECRETS),
        "replication_locations": [],
        "accessor_members": [ACCESSOR_MEMBER],
        "environment": "test",
        "owner": "platform-team",
        "application": "terraform-adk-agent",
    }


@pytest.fixture(scope="session")
def terraform_plan(
    terraform_runner: TerraformRunner,
    terraform_variables: dict[str, Any],
) -> dict[str, Any]:
    """Create and return the Terraform execution plan."""

    result = terraform_runner.plan(
        variables=terraform_variables,
        plan_file="secret-manager-e2e.tfplan",
        refresh=False,
        lock=False,
    )

    assert result.command_result.return_code in (0, 2)
    assert result.plan_file is not None
    assert result.plan_file.exists()

    return {
        "return_code": result.command_result.return_code,
        "stdout": result.command_result.stdout,
        "stderr": result.command_result.stderr,
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


def _resource_changes(
    plan_json: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return all resource changes from the Terraform plan."""

    resources = plan_json.get("resource_changes", [])
    assert isinstance(resources, list)
    return resources


def _resources_by_type(
    plan_json: dict[str, Any],
    resource_type: str,
) -> list[dict[str, Any]]:
    """Return planned resources matching a Terraform type."""

    return [
        resource
        for resource in _resource_changes(plan_json)
        if resource.get("type") == resource_type
    ]


def _planned_values(
    resource: dict[str, Any],
) -> dict[str, Any]:
    """Return planned after-values for a resource."""

    change = resource.get("change", {})
    values = change.get("after", {})
    assert isinstance(values, dict)
    return values


def test_generated_workspace_contains_expected_files(
    secret_manager_workspace: Path,
) -> None:
    """Verify all expected files are generated."""

    generated_files = {
        path.name
        for path in secret_manager_workspace.iterdir()
        if path.is_file()
    }

    assert not (EXPECTED_FILES - generated_files)


def test_generated_configuration_contains_expected_resources(
    secret_manager_workspace: Path,
) -> None:
    """Verify generated Secret Manager resource structure."""

    main_tf = (
        secret_manager_workspace / "main.tf"
    ).read_text(encoding="utf-8")

    iam_tf = (
        secret_manager_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    assert 'resource "google_secret_manager_secret" "this"' in main_tf
    assert "for_each = toset(var.secret_ids)" in main_tf
    assert "secret_id = each.value" in main_tf
    assert 'dynamic "auto"' in main_tf
    assert 'dynamic "user_managed"' in main_tf

    assert (
        'resource "google_secret_manager_secret_iam_member" "accessor"'
        in iam_tf
    )


def test_generated_configuration_does_not_store_secret_material(
    secret_manager_workspace: Path,
) -> None:
    """Verify no secret values or versions are generated."""

    terraform_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in secret_manager_workspace.glob("*.tf")
    )

    assert "google_secret_manager_secret_version" not in terraform_text
    assert "secret_data" not in terraform_text


def test_generated_configuration_does_not_allow_public_access(
    secret_manager_workspace: Path,
) -> None:
    """Verify public principals are absent from Terraform files."""

    terraform_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in secret_manager_workspace.glob("*.tf")
    )

    assert "allUsers" not in terraform_text
    assert "allAuthenticatedUsers" not in terraform_text


def test_generated_configuration_uses_least_privilege_role(
    secret_manager_workspace: Path,
) -> None:
    """Verify the generated IAM role is least privilege."""

    iam_tf = (
        secret_manager_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    assert "roles/secretmanager.secretAccessor" in iam_tf
    assert "roles/owner" not in iam_tf
    assert "roles/editor" not in iam_tf


def test_terraform_formatting(
    terraform_runner: TerraformRunner,
) -> None:
    """Verify generated Terraform files are formatted."""

    result = terraform_runner.fmt(check=True)
    assert result.return_code == 0


def test_terraform_initialization(
    terraform_runner: TerraformRunner,
) -> None:
    """Verify Terraform initializes successfully."""

    result = terraform_runner.init()
    assert result.return_code == 0


def test_terraform_validation(
    terraform_runner: TerraformRunner,
) -> None:
    """Verify generated Terraform configuration is valid."""

    result = terraform_runner.validate()
    assert result.return_code == 0


def test_terraform_plan(
    terraform_plan: dict[str, Any],
) -> None:
    """Verify Terraform creates a successful plan."""

    assert terraform_plan["return_code"] in (0, 2)
    assert terraform_plan["plan_path"].exists()


def test_plan_contains_expected_secret_resources(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the plan contains exactly the expected secrets."""

    resources = _resources_by_type(
        terraform_plan_json,
        SECRET_RESOURCE_TYPE,
    )

    actual_secret_ids = {
        _planned_values(resource).get("secret_id")
        for resource in resources
    }

    assert actual_secret_ids == EXPECTED_SECRETS


def test_plan_uses_automatic_replication(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify empty replication locations resolve to auto replication."""

    resources = _resources_by_type(
        terraform_plan_json,
        SECRET_RESOURCE_TYPE,
    )

    assert len(resources) == len(EXPECTED_SECRETS)

    for resource in resources:
        replication = _planned_values(resource).get("replication")

        assert isinstance(replication, list)
        assert len(replication) == 1

        replication_block = replication[0]
        assert isinstance(replication_block, dict)

        auto = replication_block.get("auto")
        user_managed = replication_block.get("user_managed")

        assert isinstance(auto, list)
        assert len(auto) == 1
        assert user_managed in (None, [])


def test_plan_contains_least_privilege_iam_bindings(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the plan contains one accessor binding per secret."""

    resources = _resources_by_type(
        terraform_plan_json,
        IAM_RESOURCE_TYPE,
    )

    assert len(resources) == len(EXPECTED_SECRETS)

    for resource in resources:
        values = _planned_values(resource)

        assert values.get("role") == (
            "roles/secretmanager.secretAccessor"
        )
        assert values.get("member") == ACCESSOR_MEMBER


def test_export_secret_manager_plan_summary(
    secret_manager_workspace: Path,
    terraform_plan_json: dict[str, Any],
) -> None:
    """Export a concise JSON summary of the Terraform plan."""

    secret_resources = _resources_by_type(
        terraform_plan_json,
        SECRET_RESOURCE_TYPE,
    )

    iam_resources = _resources_by_type(
        terraform_plan_json,
        IAM_RESOURCE_TYPE,
    )

    summary = {
        "workspace": WORKSPACE_NAME,
        "secret_count": len(secret_resources),
        "iam_binding_count": len(iam_resources),
        "secret_ids": sorted(
            _planned_values(resource).get("secret_id")
            for resource in secret_resources
        ),
        "secret_material_managed_by_terraform": False,
    }

    summary_path = (
        secret_manager_workspace
        / "secret-manager-plan-summary.json"
    )

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    assert summary_path.exists()
    assert summary_path.stat().st_size > 0
    assert summary["secret_count"] == 2
    assert summary["iam_binding_count"] == 2
    assert set(summary["secret_ids"]) == EXPECTED_SECRETS

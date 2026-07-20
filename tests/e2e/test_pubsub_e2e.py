"""Offline end-to-end tests for the generated Pub/Sub Terraform workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.terraform_runner import TerraformRunner


WORKSPACE_NAME = "pubsub-e2e-test"

EXPECTED_FILES = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "subscriptions.tf",
    "iam.tf",
    "outputs.tf",
    "terraform.tfvars.example",
    "README.md",
}

EXPECTED_TOPICS = {
    "order-events",
    "audit-events",
}

EXPECTED_SUBSCRIPTIONS = {
    "order-events-sub",
    "audit-events-sub",
}

EXPECTED_ACK_DEADLINES = {
    "order-events-sub": 30,
    "audit-events-sub": 20,
}

TOPIC_RESOURCE_TYPE = "google_pubsub_topic"
SUBSCRIPTION_RESOURCE_TYPE = "google_pubsub_subscription"
TOPIC_IAM_RESOURCE_TYPE = "google_pubsub_topic_iam_member"
SUBSCRIPTION_IAM_RESOURCE_TYPE = "google_pubsub_subscription_iam_member"


@pytest.fixture(scope="session")
def repository_root() -> Path:
    """Return the repository root directory."""

    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def pubsub_workspace(repository_root: Path) -> Path:
    """Return the generated Pub/Sub Terraform workspace."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    assert workspace.exists(), (
        f"Generated Pub/Sub workspace does not exist: {workspace}"
    )

    assert workspace.is_dir(), (
        f"Generated Pub/Sub workspace is not a directory: {workspace}"
    )

    return workspace


@pytest.fixture(scope="session")
def terraform_runner(
    pubsub_workspace: Path,
) -> TerraformRunner:
    """Create a Terraform runner for the Pub/Sub workspace."""

    return TerraformRunner(pubsub_workspace)


@pytest.fixture(scope="session")
def terraform_variables() -> dict[str, Any]:
    """Return variables used during Terraform plan validation.

    PUBSUB_E2E_PROJECT_ID must reference an accessible Google Cloud
    project because the generated Pub/Sub configuration currently uses
    data.google_project.this to obtain the project number.
    """

    project_id = os.getenv("PUBSUB_E2E_PROJECT_ID")

    if not project_id:
        pytest.skip(
            "PUBSUB_E2E_PROJECT_ID is not configured. "
            "Set it to an accessible Google Cloud project ID before "
            "running Pub/Sub Terraform plan tests."
        )

    return {
        "project_id": project_id,
    }


@pytest.fixture(scope="session")
def terraform_plan(
    terraform_runner: TerraformRunner,
    terraform_variables: dict[str, Any],
) -> dict[str, Any]:
    """Create and return the Terraform plan result."""

    result = terraform_runner.plan(
        variables=terraform_variables,
        plan_file="pubsub-e2e.tfplan",
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
    """Return resource changes from a Terraform plan."""

    resource_changes = plan_json.get("resource_changes", [])

    assert isinstance(resource_changes, list)

    return resource_changes


def _resources_by_type(
    plan_json: dict[str, Any],
    resource_type: str,
) -> list[dict[str, Any]]:
    """Return planned resources matching a Terraform resource type."""

    return [
        resource
        for resource in _resource_changes(plan_json)
        if resource.get("type") == resource_type
    ]


def _planned_values(
    resource: dict[str, Any],
) -> dict[str, Any]:
    """Return the planned after-values for a resource."""

    change = resource.get("change", {})
    after = change.get("after", {})

    assert isinstance(after, dict)

    return after


def _planned_resource_names(
    plan_json: dict[str, Any],
    resource_type: str,
) -> set[str]:
    """Return names from planned resources of the requested type."""

    names: set[str] = set()

    for resource in _resources_by_type(
        plan_json,
        resource_type,
    ):
        values = _planned_values(resource)
        name = values.get("name")

        if isinstance(name, str):
            names.add(name)

    return names


def test_generated_workspace_contains_expected_files(
    pubsub_workspace: Path,
) -> None:
    """Verify all expected Terraform files were generated."""

    generated_files = {
        path.name
        for path in pubsub_workspace.iterdir()
        if path.is_file()
    }

    missing_files = EXPECTED_FILES - generated_files

    assert not missing_files, (
        "Generated Pub/Sub workspace is missing files: "
        f"{sorted(missing_files)}"
    )


def test_generated_configuration_contains_expected_resources(
    pubsub_workspace: Path,
) -> None:
    """Verify generated Pub/Sub resource structures."""

    main_tf = (
        pubsub_workspace / "main.tf"
    ).read_text(encoding="utf-8")

    subscriptions_tf = (
        pubsub_workspace / "subscriptions.tf"
    ).read_text(encoding="utf-8")

    iam_tf = (
        pubsub_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    assert 'resource "google_pubsub_topic" "this"' in main_tf
    assert "for_each = toset(var.topics)" in main_tf
    assert "name    = each.value" in main_tf

    assert (
        'resource "google_pubsub_subscription" "this"'
        in subscriptions_tf
    )
    assert "for_each = var.subscriptions" in subscriptions_tf
    assert "name" in subscriptions_tf
    assert "each.key" in subscriptions_tf
    assert "each.value.topic" in subscriptions_tf

    assert (
        'resource "google_pubsub_topic_iam_member" "publishers"'
        in iam_tf
    )
    assert (
        'resource '
        '"google_pubsub_subscription_iam_member" '
        '"subscribers"'
        in iam_tf
    )


def test_generated_configuration_does_not_allow_public_access(
    pubsub_workspace: Path,
) -> None:
    """Verify generated IAM configuration has no public principals."""

    terraform_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in pubsub_workspace.glob("*.tf")
    )

    assert "allUsers" not in terraform_text
    assert "allAuthenticatedUsers" not in terraform_text


def test_generated_subscriptions_use_variable_ack_deadlines(
    pubsub_workspace: Path,
) -> None:
    """Verify acknowledgement deadlines are variable-driven."""

    subscriptions_tf = (
        pubsub_workspace / "subscriptions.tf"
    ).read_text(encoding="utf-8")

    assert "ack_deadline_seconds" in subscriptions_tf
    assert "each.value.ack_deadline_seconds" in subscriptions_tf


def test_generated_configuration_contains_expected_iam_roles(
    pubsub_workspace: Path,
) -> None:
    """Verify least-privilege Pub/Sub IAM roles are generated."""

    iam_tf = (
        pubsub_workspace / "iam.tf"
    ).read_text(encoding="utf-8")

    assert "roles/pubsub.publisher" in iam_tf
    assert "roles/pubsub.subscriber" in iam_tf


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
    """Verify Terraform creates a successful execution plan."""

    assert terraform_plan["return_code"] in (0, 2)
    assert terraform_plan["plan_path"].exists()


def test_plan_contains_expected_topic_resources(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the Terraform plan contains expected Pub/Sub topics."""

    topic_names = _planned_resource_names(
        terraform_plan_json,
        TOPIC_RESOURCE_TYPE,
    )

    assert topic_names == EXPECTED_TOPICS


def test_plan_contains_expected_subscription_resources(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify the Terraform plan contains expected subscriptions."""

    subscription_names = _planned_resource_names(
        terraform_plan_json,
        SUBSCRIPTION_RESOURCE_TYPE,
    )

    assert subscription_names == EXPECTED_SUBSCRIPTIONS


def test_plan_uses_expected_ack_deadlines(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify resolved subscription acknowledgement deadlines."""

    actual_ack_deadlines: dict[str, int] = {}

    for resource in _resources_by_type(
        terraform_plan_json,
        SUBSCRIPTION_RESOURCE_TYPE,
    ):
        values = _planned_values(resource)

        name = values.get("name")
        ack_deadline = values.get("ack_deadline_seconds")

        assert isinstance(name, str)
        assert isinstance(ack_deadline, int)

        actual_ack_deadlines[name] = ack_deadline

    assert actual_ack_deadlines == EXPECTED_ACK_DEADLINES


def test_plan_contains_least_privilege_iam_bindings(
    terraform_plan_json: dict[str, Any],
) -> None:
    """Verify planned IAM bindings use expected roles."""

    topic_iam_resources = _resources_by_type(
        terraform_plan_json,
        TOPIC_IAM_RESOURCE_TYPE,
    )

    subscription_iam_resources = _resources_by_type(
        terraform_plan_json,
        SUBSCRIPTION_IAM_RESOURCE_TYPE,
    )

    assert len(topic_iam_resources) == 2
    assert len(subscription_iam_resources) == 2

    topic_roles = {
        _planned_values(resource).get("role")
        for resource in topic_iam_resources
    }

    subscription_roles = {
        _planned_values(resource).get("role")
        for resource in subscription_iam_resources
    }

    assert topic_roles == {"roles/pubsub.publisher"}
    assert subscription_roles == {"roles/pubsub.subscriber"}

    all_iam_resources = (
        topic_iam_resources
        + subscription_iam_resources
    )

    for resource in all_iam_resources:
        member = _planned_values(resource).get("member")

        assert isinstance(member, str)
        assert member not in {
            "allUsers",
            "allAuthenticatedUsers",
        }


def test_export_pubsub_plan_summary(
    pubsub_workspace: Path,
    terraform_plan_json: dict[str, Any],
) -> None:
    """Export a concise JSON summary of the Pub/Sub plan."""

    topic_resources = _resources_by_type(
        terraform_plan_json,
        TOPIC_RESOURCE_TYPE,
    )

    subscription_resources = _resources_by_type(
        terraform_plan_json,
        SUBSCRIPTION_RESOURCE_TYPE,
    )

    topic_iam_resources = _resources_by_type(
        terraform_plan_json,
        TOPIC_IAM_RESOURCE_TYPE,
    )

    subscription_iam_resources = _resources_by_type(
        terraform_plan_json,
        SUBSCRIPTION_IAM_RESOURCE_TYPE,
    )

    summary = {
        "workspace": WORKSPACE_NAME,
        "topic_count": len(topic_resources),
        "subscription_count": len(subscription_resources),
        "topic_iam_binding_count": len(topic_iam_resources),
        "subscription_iam_binding_count": len(
            subscription_iam_resources
        ),
        "topics": sorted(
            _planned_resource_names(
                terraform_plan_json,
                TOPIC_RESOURCE_TYPE,
            )
        ),
        "subscriptions": sorted(
            _planned_resource_names(
                terraform_plan_json,
                SUBSCRIPTION_RESOURCE_TYPE,
            )
        ),
    }

    summary_path = (
        pubsub_workspace / "pubsub-plan-summary.json"
    )

    summary_path.write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    assert summary_path.exists()
    assert summary_path.stat().st_size > 0
    assert summary["topic_count"] == 2
    assert summary["subscription_count"] == 2
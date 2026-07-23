"""Tests for the v0.9.4 IAM generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("iam")
    values = {
        "region": "asia-south1",
        "service_account_id": "app-runtime-sa",
        "project_roles": [
            "roles/cloudsql.client",
            "roles/secretmanager.secretAccessor",
        ],
        "environment": "dev",
        "owner": "platform-team",
        "application": "application-api",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-iam-v094",
            values=values,
        )
    )


def test_iam_plugin_is_registered() -> None:
    assert "iam" in generator_registry.list_services()


def test_iam_generates_required_files() -> None:
    assert set(_project().files) == {
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


def test_iam_creates_dedicated_service_account() -> None:
    main_tf = _project().files["main.tf"]
    assert "google_service_account" in main_tf
    assert "app-runtime-sa" in _project().files[
        "terraform.tfvars.example"
    ]


def test_iam_grants_least_privilege_project_roles() -> None:
    project_iam_tf = _project().files["project_iam.tf"]
    assert "google_project_iam_member" in project_iam_tf
    assert "roles/owner" in project_iam_tf  # part of the precondition check
    assert "precondition" in project_iam_tf


def test_iam_rejects_owner_role() -> None:
    with pytest.raises(ValueError):
        _project(project_roles=["roles/owner"])


def test_iam_rejects_editor_role() -> None:
    with pytest.raises(ValueError):
        _project(project_roles=["roles/editor"])


def test_iam_rejects_empty_project_roles() -> None:
    with pytest.raises(ValueError):
        _project(project_roles=[])


def test_iam_rejects_duplicate_project_roles() -> None:
    with pytest.raises(ValueError):
        _project(project_roles=["roles/cloudsql.client", "roles/cloudsql.client"])


def test_iam_rejects_invalid_service_account_id() -> None:
    with pytest.raises(ValueError):
        _project(service_account_id="A")


def test_iam_scoped_impersonation_bindings() -> None:
    project = _project(
        impersonators=[
            "serviceAccount:deployer@my-project.iam.gserviceaccount.com"
        ]
    )
    impersonation_tf = project.files["impersonation.tf"]
    variables_tf = project.files["variables.tf"]
    assert "google_service_account_iam_member" in impersonation_tf
    assert "role                = var.impersonation_role" in (
        impersonation_tf
    )
    assert 'default     = "roles/iam.serviceAccountUser"' in variables_tf
    assert "service_account_id = google_service_account.this.name" in (
        impersonation_tf
    )


def test_iam_rejects_public_impersonators() -> None:
    with pytest.raises(ValueError):
        _project(impersonators=["allUsers"])

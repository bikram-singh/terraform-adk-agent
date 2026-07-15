"""Tests for the v0.9.3 Secret Manager generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("secret-manager")
    values = {
        "region": "asia-south1",
        "secret_ids": ["database-password", "api-key"],
        "accessor_members": [
            "serviceAccount:runtime@my-project.iam.gserviceaccount.com"
        ],
        "environment": "dev",
        "owner": "platform-team",
        "application": "application-api",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-secret-manager-v093",
            values=values,
        )
    )


def test_secret_manager_plugin_is_registered() -> None:
    assert "secret-manager" in generator_registry.list_services()


def test_secret_manager_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_secret_manager_creates_one_secret_per_id() -> None:
    main_tf = _project().files["main.tf"]
    assert "google_secret_manager_secret" in main_tf
    assert "for_each = toset(var.secret_ids)" in main_tf
    assert '"database-password"' in _project().files[
        "terraform.tfvars.example"
    ]


def test_secret_manager_does_not_generate_secret_material() -> None:
    project = _project()
    assert "google_secret_manager_secret_version" not in project.files[
        "main.tf"
    ]
    for content in project.files.values():
        assert "secret_data" not in content


def test_secret_manager_grants_least_privilege_access() -> None:
    iam_tf = _project().files["iam.tf"]
    assert "google_secret_manager_secret_iam_member" in iam_tf
    assert "roles/secretmanager.secretAccessor" in iam_tf


def test_secret_manager_supports_user_managed_replication() -> None:
    project = _project(replication_locations=["asia-south1", "us-central1"])
    assert "user_managed" in project.files["main.tf"]
    assert "asia-south1" in project.files["terraform.tfvars.example"]


def test_secret_manager_rejects_empty_secret_ids() -> None:
    with pytest.raises(ValueError):
        _project(secret_ids=[])


def test_secret_manager_rejects_duplicate_secret_ids() -> None:
    with pytest.raises(ValueError):
        _project(secret_ids=["dup", "dup"])


def test_secret_manager_rejects_invalid_secret_id() -> None:
    with pytest.raises(ValueError):
        _project(secret_ids=["bad id!"])


def test_secret_manager_rejects_public_accessor_members() -> None:
    with pytest.raises(ValueError):
        _project(accessor_members=["allUsers"])


def test_secret_manager_rejects_malformed_accessor_member() -> None:
    with pytest.raises(ValueError):
        _project(accessor_members=["not-a-valid-member"])

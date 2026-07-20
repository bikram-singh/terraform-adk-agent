"""Unit tests for the Secret Manager Terraform generator."""

from __future__ import annotations

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.secret_manager.generator import SecretManagerGenerator


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


def _generate_project(
    *,
    secret_ids: list[str] | None = None,
    replication_locations: list[str] | None = None,
    accessor_members: list[str] | None = None,
):
    generator = SecretManagerGenerator()

    return generator.generate(
        GeneratorContext(
            workspace_name="secret-manager-unit-test",
            values={
                "region": "asia-south1",
                "secret_ids": (
                    secret_ids
                    if secret_ids is not None
                    else ["database-password", "api-token"]
                ),
                "replication_locations": (
                    replication_locations
                    if replication_locations is not None
                    else []
                ),
                "accessor_members": (
                    accessor_members
                    if accessor_members is not None
                    else [
                        "serviceAccount:runtime@test-project."
                        "iam.gserviceaccount.com"
                    ]
                ),
                "environment": "test",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
            },
        )
    )


def test_secret_manager_metadata() -> None:
    generator = SecretManagerGenerator()

    assert generator.metadata.service_name == "secret-manager"
    assert generator.metadata.display_name == "Google Secret Manager"
    assert set(generator.metadata.generated_files) == EXPECTED_FILES


def test_secret_manager_generates_required_files() -> None:
    project = _generate_project()

    assert set(project.files) == EXPECTED_FILES
    assert project.service == "secret-manager"


def test_secret_manager_creates_one_secret_per_id() -> None:
    project = _generate_project()
    main_tf = project.files["main.tf"]
    variables_tf = project.files["variables.tf"]

    assert 'resource "google_secret_manager_secret" "this"' in main_tf
    assert "for_each = toset(var.secret_ids)" in main_tf
    assert "secret_id = each.value" in main_tf
    assert '"database-password"' in variables_tf
    assert '"api-token"' in variables_tf


def test_secret_manager_uses_automatic_replication_by_default() -> None:
    project = _generate_project(replication_locations=[])
    main_tf = project.files["main.tf"]

    assert 'dynamic "auto"' in main_tf
    assert (
        "length(var.replication_locations) == 0 ? [1] : []"
        in main_tf
    )


def test_secret_manager_supports_user_managed_replication() -> None:
    project = _generate_project(
        replication_locations=["asia-south1", "asia-south2"]
    )

    variables_tf = project.files["variables.tf"]
    main_tf = project.files["main.tf"]

    assert '"asia-south1"' in variables_tf
    assert '"asia-south2"' in variables_tf
    assert 'dynamic "user_managed"' in main_tf
    assert "for_each = var.replication_locations" in main_tf


def test_secret_manager_grants_least_privilege_access() -> None:
    project = _generate_project()
    iam_tf = project.files["iam.tf"]

    assert (
        'resource "google_secret_manager_secret_iam_member" "accessor"'
        in iam_tf
    )
    assert 'role      = "roles/secretmanager.secretAccessor"' in iam_tf
    assert "google_secret_manager_secret.this" in iam_tf


def test_secret_manager_does_not_generate_secret_material() -> None:
    project = _generate_project()
    terraform_text = "\n".join(project.files.values())

    assert "google_secret_manager_secret_version" not in terraform_text
    assert "secret_data" not in terraform_text
    assert "database-password-value" not in terraform_text


def test_secret_manager_adds_enterprise_labels() -> None:
    project = _generate_project()
    main_tf = project.files["main.tf"]

    assert "environment = var.environment" in main_tf
    assert "owner       = var.owner" in main_tf
    assert "application = var.application" in main_tf
    assert 'managed_by  = "terraform"' in main_tf


def test_secret_manager_readme_documents_secure_usage() -> None:
    project = _generate_project()
    readme = project.files["README.md"]

    assert "No secret version or secret material" in readme
    assert "gcloud secrets versions add" in readme
    assert "allUsers" in readme
    assert "allAuthenticatedUsers" in readme


def test_secret_manager_rejects_empty_secret_ids() -> None:
    with pytest.raises(
        ValueError,
        match="secret_ids must contain at least one entry",
    ):
        _generate_project(secret_ids=[])


def test_secret_manager_rejects_duplicate_secret_ids() -> None:
    with pytest.raises(
        ValueError,
        match="secret_ids must not contain duplicates",
    ):
        _generate_project(secret_ids=["api-token", "api-token"])


@pytest.mark.parametrize(
    "secret_id",
    [
        "contains space",
        "contains.dot",
        "contains/slash",
        "",
        "a" * 256,
    ],
)
def test_secret_manager_rejects_invalid_secret_ids(
    secret_id: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid secret_id"):
        _generate_project(secret_ids=[secret_id])


def test_secret_manager_rejects_duplicate_replication_locations() -> None:
    with pytest.raises(
        ValueError,
        match="replication_locations must not contain duplicates",
    ):
        _generate_project(
            replication_locations=["asia-south1", "asia-south1"]
        )


@pytest.mark.parametrize(
    "location",
    [
        "asia",
        "asia_south1",
        "ASIA-SOUTH1",
        "asia-south",
        "asia-south-1",
    ],
)
def test_secret_manager_rejects_invalid_replication_location(
    location: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="Invalid replication location",
    ):
        _generate_project(replication_locations=[location])


@pytest.mark.parametrize(
    "member",
    [
        "allUsers",
        "allAuthenticatedUsers",
    ],
)
def test_secret_manager_rejects_public_accessor_members(
    member: str,
) -> None:
    with pytest.raises(ValueError):
        _generate_project(accessor_members=[member])


def test_secret_manager_rejects_malformed_accessor_member() -> None:
    with pytest.raises(ValueError):
        _generate_project(accessor_members=["runtime@test-project"])


def test_secret_manager_normalizes_labels() -> None:
    generator = SecretManagerGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name="secret-manager-label-test",
            values={
                "secret_ids": ["api-token"],
                "environment": "QA Environment",
                "owner": "Platform Team",
                "application": "Terraform ADK Agent",
            },
        )
    )

    variables_tf = project.files["variables.tf"]

    assert 'default     = "qa-environment"' in variables_tf
    assert 'default     = "platform-team"' in variables_tf
    assert 'default     = "terraform-adk-agent"' in variables_tf

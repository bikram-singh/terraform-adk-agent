"""Tests for the Artifact Registry generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("artifact-registry")
    values = {
        "region": "asia-south1",
        "repository_id": "unit-images",
        "environment": "dev",
        "owner": "platform-team",
        "application": "unit-test",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-artifact-registry",
            values=values,
        )
    )


def test_artifact_registry_plugin_is_registered() -> None:
    assert "artifact-registry" in generator_registry.list_services()


def test_artifact_registry_generates_required_files() -> None:
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


def test_artifact_registry_defaults_to_docker_format() -> None:
    variables_tf = _project().files["variables.tf"]
    assert 'default     = "DOCKER"' in variables_tf


def test_artifact_registry_rejects_unsupported_format() -> None:
    with pytest.raises(ValueError):
        _project(format="RUBYGEMS")


def test_artifact_registry_accepts_all_documented_formats() -> None:
    for fmt in ("DOCKER", "MAVEN", "NPM", "PYTHON", "APT", "YUM", "GENERIC"):
        project = _project(format=fmt)
        assert f'default     = "{fmt}"' in project.files["variables.tf"]


def test_artifact_registry_rejects_invalid_repository_id() -> None:
    with pytest.raises(ValueError):
        _project(repository_id="Invalid_ID_With_Caps")


def test_artifact_registry_rejects_empty_repository_id() -> None:
    with pytest.raises(ValueError):
        _project(repository_id="")


def test_artifact_registry_rejects_public_reader_member() -> None:
    with pytest.raises(ValueError):
        _project(reader_members=["allUsers"])


def test_artifact_registry_rejects_public_writer_member() -> None:
    with pytest.raises(ValueError):
        _project(writer_members=["allAuthenticatedUsers"])


def test_artifact_registry_reader_and_writer_iam_bindings_present() -> None:
    iam_tf = _project(
        reader_members=["serviceAccount:reader@test.iam.gserviceaccount.com"],
        writer_members=["serviceAccount:writer@test.iam.gserviceaccount.com"],
    ).files["iam.tf"]

    assert "google_artifact_registry_repository_iam_member" in iam_tf
    assert "roles/artifactregistry.reader" in iam_tf
    assert "roles/artifactregistry.writer" in iam_tf


def test_artifact_registry_cleanup_policy_dry_run_defaults_true() -> None:
    variables_tf = _project().files["variables.tf"]
    assert 'variable "cleanup_policy_dry_run"' in variables_tf
    # Find the default within this specific variable block only.
    block = variables_tf.split('variable "cleanup_policy_dry_run"')[1]
    block = block.split("}")[0]
    assert "default     = true" in block


def test_artifact_registry_cleanup_policy_rejects_zero_keep_count() -> None:
    with pytest.raises(ValueError):
        _project(cleanup_policy_keep_count=0)


def test_artifact_registry_default_reader_and_writer_members_are_empty() -> None:
    variables_tf = _project().files["variables.tf"]
    assert "default     = []" in variables_tf


def test_artifact_registry_non_empty_and_empty_lists_both_format_correctly() -> None:
    """Regression check for the terraform fmt alignment bug fixed
    earlier this session: reader_members (non-empty here) must render
    single-spaced, writer_members (empty here) must render aligned."""

    variables_tf = _project(
        reader_members=["serviceAccount:reader@test.iam.gserviceaccount.com"],
    ).files["variables.tf"]

    reader_block = variables_tf.split('variable "reader_members"')[1].split(
        "}"
    )[0]
    writer_block = variables_tf.split('variable "writer_members"')[1].split(
        "}"
    )[0]

    assert "default = [" in reader_block
    assert "default     = []" in writer_block

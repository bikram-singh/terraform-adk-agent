"""Tests for the Cloud Functions (2nd gen) generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("cloud-functions")
    values = {
        "region": "asia-south1",
        "function_name": "order-events",
        "environment": "dev",
        "owner": "platform-team",
        "application": "order-events",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-cloud-functions",
            values=values,
        )
    )


def test_cloud_functions_plugin_is_registered() -> None:
    assert "cloud-functions" in generator_registry.list_services()


def test_cloud_functions_generates_required_files() -> None:
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


def test_cloud_functions_creates_source_bucket_and_function() -> None:
    main_tf = _project().files["main.tf"]
    assert "google_storage_bucket" in main_tf
    assert "google_storage_bucket_object" in main_tf
    assert "google_cloudfunctions2_function" in main_tf
    assert "uniform_bucket_level_access = true" in main_tf
    assert 'public_access_prevention    = "enforced"' in main_tf


def test_cloud_functions_is_private_by_default() -> None:
    variables_tf = _project().files["variables.tf"]
    assert 'default     = "ALLOW_INTERNAL_ONLY"' in variables_tf
    tfvars = _project().files["terraform.tfvars.example"]
    assert "allow_unauthenticated = false" in tfvars


def test_cloud_functions_creates_dedicated_service_account() -> None:
    iam_tf = _project().files["iam.tf"]
    assert "google_service_account" in iam_tf
    assert "google_secret_manager_secret_iam_member" in iam_tf
    assert "google_cloudfunctions2_function_iam_member" in iam_tf


def test_cloud_functions_does_not_generate_secret_material() -> None:
    project = _project()
    for content in project.files.values():
        assert "secret_data" not in content


def test_cloud_functions_rejects_invalid_function_name() -> None:
    with pytest.raises(ValueError):
        _project(function_name="Bad Name!")


def test_cloud_functions_rejects_invalid_ingress_settings() -> None:
    with pytest.raises(ValueError):
        _project(ingress_settings="ALLOW_EVERYTHING")


def test_cloud_functions_rejects_invalid_scaling() -> None:
    with pytest.raises(ValueError):
        _project(min_instance_count=5, max_instance_count=1)


def test_cloud_functions_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError):
        _project(timeout_seconds=999999)


def test_cloud_functions_allow_unauthenticated_flag() -> None:
    project = _project(allow_unauthenticated=True)
    assert "Public invocation was explicitly enabled" in " ".join(
        project.diagnostics
    )

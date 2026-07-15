"""Regression tests for the GCS Terraform generator."""

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.gcs.generator import GCSGenerator


def _generate_project(
    *,
    location: str = "asia-south1",
    storage_class: str = "STANDARD",
):
    generator = GCSGenerator()

    context = GeneratorContext(
        workspace_name="gcs-generator-test",
        values={
            "project_id": "example-project",
            "bucket_name": "example-secure-bucket",
            "location": location,
            "storage_class": storage_class,
            "environment": "test",
            "owner": "platform-team",
            "application": "terraform-adk-agent",
            "noncurrent_version_retention_days": 30,
        },
    )

    return generator.generate(context)


def test_gcs_generator_uses_location_not_region():
    project = _generate_project()

    variables = project.files["variables.tf"]
    main = project.files["main.tf"]
    providers = project.files["providers.tf"]
    tfvars = project.files["terraform.tfvars.example"]

    assert 'variable "location"' in variables
    assert 'variable "region"' not in variables
    assert "location      = var.location" in main
    assert "var.region" not in main
    assert "var.region" not in providers
    assert 'location      = "asia-south1"' in tfvars
    assert "region" not in tfvars


def test_gcs_generator_supports_storage_class():
    project = _generate_project(storage_class="NEARLINE")

    variables = project.files["variables.tf"]
    main = project.files["main.tf"]
    tfvars = project.files["terraform.tfvars.example"]

    assert 'variable "storage_class"' in variables
    assert 'default     = "NEARLINE"' in variables
    assert "storage_class = var.storage_class" in main
    assert 'storage_class = "NEARLINE"' in tfvars


def test_gcs_generator_enforces_secure_bucket_defaults():
    project = _generate_project()

    main = project.files["main.tf"]

    assert "uniform_bucket_level_access = true" in main
    assert 'public_access_prevention    = "enforced"' in main
    assert "force_destroy               = false" in main
    assert "enabled = true" in main
    assert 'managed_by  = "terraform-adk-agent"' in main


def test_gcs_generator_adds_retention_validation():
    project = _generate_project()

    variables = project.files["variables.tf"]

    assert "var.noncurrent_version_retention_days >= 1" in variables
    assert "Retention days must be at least 1." in variables


def test_gcs_generator_accepts_legacy_region_input():
    generator = GCSGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name="legacy-region-test",
            values={
                "project_id": "example-project",
                "bucket_name": "example-legacy-bucket",
                "region": "us-central1",
                "storage_class": "STANDARD",
                "environment": "test",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
                "noncurrent_version_retention_days": 30,
            },
        )
    )

    assert 'default     = "us-central1"' in project.files["variables.tf"]
    assert 'location      = "us-central1"' in (
        project.files["terraform.tfvars.example"]
    )


def test_gcs_generator_rejects_invalid_storage_class():
    with pytest.raises(
        ValueError,
        match="storage_class must be one of",
    ):
        _generate_project(storage_class="INVALID")


def test_gcs_generator_rejects_invalid_retention_days():
    generator = GCSGenerator()

    with pytest.raises(
        ValueError,
        match="noncurrent_version_retention_days must be at least 1",
    ):
        generator.generate(
            GeneratorContext(
                workspace_name="invalid-retention-test",
                values={
                    "project_id": "example-project",
                    "bucket_name": "example-invalid-retention-bucket",
                    "location": "asia-south1",
                    "storage_class": "STANDARD",
                    "environment": "test",
                    "owner": "platform-team",
                    "application": "terraform-adk-agent",
                    "noncurrent_version_retention_days": 0,
                },
            )
        )
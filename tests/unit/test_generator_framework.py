"""Unit tests for the v0.5 multi-service generator framework."""

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def test_gcs_plugin_is_registered() -> None:
    assert "gcs" in generator_registry.list_services()


def test_registry_exposes_metadata() -> None:
    metadata = generator_registry.metadata()

    assert metadata[0]["service_name"] == "gcs"
    assert "google_storage_bucket.this" in metadata[0]["resources"]


def test_gcs_plugin_generates_required_files() -> None:
    generator = generator_registry.get("gcs")

    project = generator.generate(
        GeneratorContext(
            workspace_name="unit-gcs-v05",
            values={
                "project_id": "example-project",
                "bucket_name": "example-unit-gcs-v05-bucket",
                "location": "asia-south1",
                "storage_class": "STANDARD",
                "environment": "dev",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
                "noncurrent_version_retention_days": 30,
            },
        )
    )

    assert set(project.files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_gcs_plugin_enforces_secure_defaults() -> None:
    generator = generator_registry.get("gcs")

    project = generator.generate(
        GeneratorContext(
            workspace_name="unit-gcs-secure-v05",
            values={
                "project_id": "example-project",
                "bucket_name": "example-unit-gcs-secure-v05-bucket",
                "location": "asia-south1",
                "storage_class": "STANDARD",
            },
        )
    )

    main_tf = project.files["main.tf"]

    assert 'public_access_prevention    = "enforced"' in main_tf
    assert "uniform_bucket_level_access = true" in main_tf
    assert "force_destroy               = false" in main_tf
    assert "allUsers" not in main_tf
    assert "allAuthenticatedUsers" not in main_tf
    assert "versioning {" in main_tf
    assert "enabled = true" in main_tf


def test_gcs_plugin_uses_requested_location_and_storage_class() -> None:
    generator = generator_registry.get("gcs")

    project = generator.generate(
        GeneratorContext(
            workspace_name="unit-gcs-location-storage-v05",
            values={
                "project_id": "example-project",
                "bucket_name": "example-location-storage-bucket",
                "location": "asia-south1",
                "storage_class": "NEARLINE",
            },
        )
    )

    variables_tf = project.files["variables.tf"]
    main_tf = project.files["main.tf"]
    tfvars_example = project.files["terraform.tfvars.example"]

    assert 'variable "location"' in variables_tf
    assert 'variable "storage_class"' in variables_tf
    assert "location      = var.location" in main_tf
    assert "storage_class = var.storage_class" in main_tf
    assert 'location      = "asia-south1"' in tfvars_example
    assert 'storage_class = "NEARLINE"' in tfvars_example
    assert "var.region" not in main_tf


def test_gcs_plugin_renders_project_and_bucket_values() -> None:
    generator = generator_registry.get("gcs")

    project = generator.generate(
        GeneratorContext(
            workspace_name="unit-gcs-rendered-values-v05",
            values={
                "project_id": "example-project",
                "bucket_name": "example-rendered-values-bucket",
                "location": "asia-south1",
                "storage_class": "STANDARD",
            },
        )
    )

    tfvars_example = project.files["terraform.tfvars.example"]

    assert 'project_id    = "example-project"' in tfvars_example
    assert (
        'bucket_name   = "example-rendered-values-bucket"'
        in tfvars_example
    )
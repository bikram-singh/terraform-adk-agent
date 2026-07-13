"""Unit tests for the v0.5 multi-service generator framework."""

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def test_gcs_plugin_is_registered() -> None:
    assert generator_registry.list_services() == ("gcs",)


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
                "region": "asia-south1",
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
            values={"region": "asia-south1"},
        )
    )

    main_tf = project.files["main.tf"]
    assert 'public_access_prevention    = "enforced"' in main_tf
    assert "uniform_bucket_level_access = true" in main_tf
    assert "force_destroy               = false" in main_tf
    assert "allUsers" not in main_tf

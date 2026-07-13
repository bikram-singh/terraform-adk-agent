"""Unit tests for the v0.6 Cloud Run generator plugin."""
from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project():
    return generator_registry.get("cloud-run").generate(
        GeneratorContext(
            workspace_name="unit-cloud-run-v06",
            values={
                "region": "asia-south1",
                "service_name": "sample-service",
                "container_image": (
                    "asia-south1-docker.pkg.dev/"
                    "sample-project/apps/sample-service:1.0.0"
                ),
                "environment": "dev",
                "owner": "platform-team",
                "application": "sample-service",
                "container_port": 8080,
                "cpu": "1",
                "memory": "512Mi",
                "min_instances": 0,
                "max_instances": 5,
            },
        )
    )


def test_cloud_run_plugin_is_registered() -> None:
    assert "cloud-run" in generator_registry.list_services()


def test_cloud_run_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf", "providers.tf", "variables.tf", "main.tf",
        "iam.tf", "outputs.tf", "terraform.tfvars.example", "README.md",
    }


def test_cloud_run_uses_v2_and_dedicated_service_account() -> None:
    project = _project()
    assert 'resource "google_cloud_run_v2_service" "this"' in project.files["main.tf"]
    assert 'resource "google_service_account" "runtime"' in project.files["iam.tf"]
    assert "service_account = google_service_account.runtime.email" in project.files["main.tf"]


def test_cloud_run_is_private_and_protected_by_default() -> None:
    tfvars = _project().files["terraform.tfvars.example"]
    assert "allow_unauthenticated = false" in tfvars
    assert "deletion_protection   = true" in tfvars


def test_cloud_run_supports_optional_integrations() -> None:
    project = _project()
    assert 'dynamic "vpc_access"' in project.files["main.tf"]
    assert 'dynamic "volumes"' in project.files["main.tf"]
    assert "secret_environment_variables" in project.files["main.tf"]
    assert "roles/cloudsql.client" in project.files["iam.tf"]
    assert "roles/secretmanager.secretAccessor" in project.files["iam.tf"]

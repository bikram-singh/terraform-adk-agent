"""Unit tests for the v0.8 GKE generator plugin."""

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project():
    generator = generator_registry.get("gke")
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-gke-v08",
            values={
                "region": "asia-south1",
                "cluster_name": "platform-gke",
                "cluster_mode": "STANDARD",
                "environment": "dev",
                "owner": "platform-team",
                "application": "platform-gke",
                "node_min_count": 1,
                "node_max_count": 3,
            },
        )
    )


def test_gke_plugin_is_registered() -> None:
    assert "gke" in generator_registry.list_services()


def test_gke_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "cluster.tf",
        "node_pool.tf",
        "iam.tf",
        "artifact_registry.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_gke_supports_standard_and_autopilot() -> None:
    cluster_tf = _project().files["cluster.tf"]

    assert 'resource "google_container_cluster" "standard"' in cluster_tf
    assert 'resource "google_container_cluster" "autopilot"' in cluster_tf
    assert "enable_autopilot = true" in cluster_tf


def test_gke_uses_secure_platform_defaults() -> None:
    cluster_tf = _project().files["cluster.tf"]
    node_pool_tf = _project().files["node_pool.tf"]

    assert "enable_private_nodes    = true" in cluster_tf
    assert "workload_identity_config" in cluster_tf
    assert "gateway_api_config" in cluster_tf
    assert "managed_prometheus" in cluster_tf
    assert "deletion_protection" in cluster_tf
    assert "enable_secure_boot          = true" in node_pool_tf
    assert 'mode = "GKE_METADATA"' in node_pool_tf


def test_invalid_cluster_mode_is_rejected() -> None:
    generator = generator_registry.get("gke")

    try:
        generator.generate(
            GeneratorContext(
                workspace_name="invalid-gke",
                values={
                    "cluster_name": "invalid-gke",
                    "cluster_mode": "UNKNOWN",
                },
            )
        )
    except ValueError as exc:
        assert "STANDARD or AUTOPILOT" in str(exc)
    else:
        raise AssertionError("Expected invalid cluster mode to fail.")

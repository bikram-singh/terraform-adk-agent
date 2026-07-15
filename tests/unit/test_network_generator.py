"""Tests for the v0.9.2 Network generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("network")
    values = {
        "region": "asia-south1",
        "network_name": "app-vpc",
        "subnet_name": "app-vpc-subnet",
        "subnet_cidr": "10.0.0.0/20",
        "private_service_access_range_name": "app-vpc-psa-range",
        "vpc_connector_name": "app-vpc-connector",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-network-v092",
            values=values,
        )
    )


def test_network_plugin_is_registered() -> None:
    assert "network" in generator_registry.list_services()


def test_network_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "network.tf",
        "private_service_access.tf",
        "vpc_connector.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_network_creates_private_vpc_and_subnet() -> None:
    network_tf = _project().files["network.tf"]
    assert "google_compute_network" in network_tf
    assert "auto_create_subnetworks  = false" in network_tf
    assert "private_ip_google_access = true" in network_tf
    assert "log_config" in network_tf


def test_network_creates_private_service_access() -> None:
    psa_tf = _project().files["private_service_access.tf"]
    assert "google_compute_global_address" in psa_tf
    assert "google_service_networking_connection" in psa_tf
    assert "servicenetworking.googleapis.com" in psa_tf


def test_network_vpc_connector_enabled_by_default() -> None:
    connector_tf = _project().files["vpc_connector.tf"]
    assert "google_vpc_access_connector" in connector_tf
    assert "count = var.enable_serverless_vpc_connector ? 1 : 0" in (
        connector_tf
    )


def test_network_vpc_connector_can_be_disabled() -> None:
    project = _project(enable_serverless_vpc_connector=False)
    assert (
        "enable_serverless_vpc_connector = false"
        in project.files["terraform.tfvars.example"]
    )
    # File is still generated, only the resource count changes at plan time.
    assert "google_vpc_access_connector" in project.files["vpc_connector.tf"]


def test_network_supports_secondary_ip_ranges() -> None:
    project = _project(
        secondary_ip_ranges={
            "pods": "10.4.0.0/14",
            "services": "10.8.0.0/20",
        }
    )
    variables_tf = project.files["variables.tf"]
    assert "secondary_ip_range" in project.files["network.tf"]
    assert "pods" in variables_tf or "pods" in project.files[
        "terraform.tfvars.example"
    ]


def test_network_rejects_invalid_subnet_cidr() -> None:
    with pytest.raises(ValueError):
        _project(subnet_cidr="not-a-cidr")


def test_network_rejects_oversized_connector_name() -> None:
    with pytest.raises(ValueError):
        _project(vpc_connector_name="a" * 26)


def test_network_rejects_connector_cidr_not_slash_28() -> None:
    with pytest.raises(ValueError):
        _project(vpc_connector_cidr="10.10.0.0/24")


def test_network_rejects_invalid_machine_type() -> None:
    with pytest.raises(ValueError):
        _project(vpc_connector_machine_type="n2-standard-2")

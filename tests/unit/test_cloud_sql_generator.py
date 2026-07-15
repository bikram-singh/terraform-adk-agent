"""Tests for the v0.9.1 Cloud SQL generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(database_version: str = "POSTGRES_16"):
    generator = generator_registry.get("cloud-sql")
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-cloud-sql-v091",
            values={
                "region": "asia-south1",
                "instance_name": "application-db",
                "database_version": database_version,
                "environment": "dev",
                "owner": "platform-team",
                "application": "application",
            },
        )
    )


def test_cloud_sql_plugin_is_registered() -> None:
    assert "cloud-sql" in generator_registry.list_services()


def test_cloud_sql_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "database.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_cloud_sql_is_private_and_protected_by_default() -> None:
    project = _project()
    assert "ipv4_enabled" in project.files["main.tf"]
    assert "private_network" in project.files["main.tf"]
    assert "deletion_protection = true" in project.files[
        "terraform.tfvars.example"
    ]


def test_cloud_sql_enables_backup_and_pitr() -> None:
    main_tf = _project().files["main.tf"]
    assert "backup_configuration" in main_tf
    assert "point_in_time_recovery_enabled" in main_tf


def test_cloud_sql_does_not_generate_password() -> None:
    project = _project()
    assert "password" not in project.files[
        "terraform.tfvars.example"
    ].lower()
    assert "google_sql_user" not in project.files["main.tf"]


@pytest.mark.parametrize(
    "database_version",
    ["POSTGRES_16", "MYSQL_8_0"],
)
def test_supported_database_families(database_version: str) -> None:
    assert _project(database_version).service == "cloud-sql"


def test_unsupported_database_family_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL or MySQL"):
        _project("SQLSERVER_2022_STANDARD")

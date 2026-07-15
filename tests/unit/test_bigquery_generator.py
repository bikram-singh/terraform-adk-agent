"""Tests for the BigQuery generator."""

import pytest

from terraform_agent.generators import generator_registry
from terraform_agent.generators.base import GeneratorContext


def _project(**overrides):
    generator = generator_registry.get("bigquery")
    values = {
        "region": "asia-south1",
        "dataset_id": "analytics",
        "environment": "dev",
        "owner": "platform-team",
        "application": "analytics",
    }
    values.update(overrides)
    return generator.generate(
        GeneratorContext(
            workspace_name="unit-bigquery",
            values=values,
        )
    )


def test_bigquery_plugin_is_registered() -> None:
    assert "bigquery" in generator_registry.list_services()


def test_bigquery_generates_required_files() -> None:
    assert set(_project().files) == {
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "tables.tf",
        "iam.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    }


def test_bigquery_uses_default_sample_table_when_omitted() -> None:
    project = _project()
    assert "events" in project.files["terraform.tfvars.example"]
    assert "google_bigquery_table" in project.files["tables.tf"]


def test_bigquery_creates_dataset_with_secure_defaults() -> None:
    main_tf = _project().files["main.tf"]
    assert "google_bigquery_dataset" in main_tf
    assert "delete_contents_on_destroy  = false" in main_tf
    tables_tf = _project().files["tables.tf"]
    assert "deletion_protection = var.deletion_protection" in tables_tf


def test_bigquery_supports_custom_tables_with_partitioning() -> None:
    project = _project(
        tables={
            "orders": {
                "schema_json": (
                    '[{"name": "order_id", "type": "STRING", '
                    '"mode": "REQUIRED"}, {"name": "placed_at", '
                    '"type": "TIMESTAMP", "mode": "REQUIRED"}]'
                ),
                "description": "Orders fact table.",
                "partitioning_field": "placed_at",
            }
        }
    )
    tables_tf = project.files["tables.tf"]
    assert "time_partitioning" in tables_tf
    assert "orders" in project.files["terraform.tfvars.example"]


def test_bigquery_rejects_invalid_dataset_id() -> None:
    with pytest.raises(ValueError):
        _project(dataset_id="1-bad-id!")


def test_bigquery_rejects_invalid_schema_json() -> None:
    with pytest.raises(ValueError):
        _project(
            tables={
                "broken": {
                    "schema_json": "not json",
                }
            }
        )


def test_bigquery_rejects_schema_json_that_is_not_an_array() -> None:
    with pytest.raises(ValueError):
        _project(
            tables={
                "broken": {
                    "schema_json": '{"name": "id"}',
                }
            }
        )


def test_bigquery_rejects_partitioning_field_not_in_schema() -> None:
    with pytest.raises(ValueError):
        _project(
            tables={
                "orders": {
                    "schema_json": (
                        '[{"name": "order_id", "type": "STRING", '
                        '"mode": "REQUIRED"}]'
                    ),
                    "partitioning_field": "does_not_exist",
                }
            }
        )


def test_bigquery_grants_least_privilege_iam() -> None:
    project = _project(
        reader_members=[
            "serviceAccount:analyst@my-project.iam.gserviceaccount.com"
        ],
        editor_members=[
            "serviceAccount:etl@my-project.iam.gserviceaccount.com"
        ],
    )
    iam_tf = project.files["iam.tf"]
    assert "roles/bigquery.dataViewer" in iam_tf
    assert "roles/bigquery.dataEditor" in iam_tf


def test_bigquery_rejects_public_reader_member() -> None:
    with pytest.raises(ValueError):
        _project(reader_members=["allUsers"])

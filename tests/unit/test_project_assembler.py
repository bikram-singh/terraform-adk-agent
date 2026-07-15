"""Tests for the v0.9.5 Project Assembler."""

import shutil

from terraform_agent.config import get_settings
from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)


def _clean_workspace(workspace_name: str) -> None:
    workspace = get_settings().output_root / workspace_name
    if workspace.exists():
        shutil.rmtree(workspace)


def test_assembler_rejects_invalid_workspace_name() -> None:
    result = assemble_private_cloud_run_cloud_sql_project(workspace_name="x")
    assert result["status"] == "error"
    assert result["stage"] == "analysis"
    assert result["deployment_performed"] is False


def test_assembler_rejects_invalid_database_version() -> None:
    result = assemble_private_cloud_run_cloud_sql_project(
        workspace_name="unit-assembler-v095-baddb",
        application="unit-app-3",
        service_name="unit-app-3",
        database_version="ORACLE_19",
    )
    assert result["status"] == "error"
    assert result["stage"] == "generation"
    assert result["deployment_performed"] is False


def test_assembler_composes_and_validates_full_architecture() -> None:
    workspace_name = "unit-assembler-v095-full"
    _clean_workspace(workspace_name)
    try:
        result = assemble_private_cloud_run_cloud_sql_project(
            workspace_name=workspace_name,
            application="unit-app",
            service_name="unit-app",
        )

        assert result["deployment_performed"] is False
        assert result["architecture_type"] == "private-cloud-run-cloud-sql"

        generated_files = set(result["plan"]["generated_files"])
        assert "main.tf" in generated_files
        assert "modules/network/network.tf" in generated_files
        assert "modules/cloud-sql/main.tf" in generated_files
        assert "modules/secret-manager/main.tf" in generated_files
        assert "modules/cloud-run/main.tf" in generated_files
        assert "modules/network/providers.tf" not in generated_files

        assert result["status"] == "success"
        assert result["validation"]["status"] == "success"
    finally:
        _clean_workspace(workspace_name)


def test_assembler_truncates_long_vpc_connector_name() -> None:
    workspace_name = "unit-assembler-v095-long"
    _clean_workspace(workspace_name)
    try:
        result = assemble_private_cloud_run_cloud_sql_project(
            workspace_name=workspace_name,
            application="a-very-long-application-name-indeed",
            service_name="a-very-long-application-name-indeed",
        )
        assert result["status"] == "success"
    finally:
        _clean_workspace(workspace_name)

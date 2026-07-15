"""Tests for the v1.0 Enterprise AI Infrastructure Architect."""

import shutil

from terraform_agent.config import get_settings
from terraform_agent.intelligence.architect import design_infrastructure


def _clean_workspace(workspace_name: str) -> None:
    workspace = get_settings().output_root / workspace_name
    if workspace.exists():
        shutil.rmtree(workspace)


def test_architect_rejects_unsupported_request() -> None:
    result = design_infrastructure(
        request="Create a BigQuery dataset for analytics.",
        workspace_name="unit-architect-v10-unsupported",
    )
    assert result["status"] == "error"
    assert result["stage"] == "intent_detection"
    assert result["architecture_type"] == "unsupported"
    assert "supported_architecture_recipes" in result
    assert "available_generators" in result
    assert result["deployment_performed"] is False


def test_architect_infers_mysql_from_request_text() -> None:
    workspace_name = "unit-architect-v10-mysql-detect"
    _clean_workspace(workspace_name)
    try:
        result = design_infrastructure(
            request=(
                "Create a private Cloud Run application connected to "
                "MySQL."
            ),
            workspace_name=workspace_name,
        )
        # Detection succeeds even though generation will run; verify the
        # inferred database engine reached the dependency graph
        # regardless of final assembly outcome.
        assert result["architecture_type"] == "private-cloud-run-cloud-sql"
        assert (
            result["dependency_graph"]["nodes"][4]["configuration"][
                "database_engine"
            ]
            == "MYSQL_8_0"
        )
    finally:
        _clean_workspace(workspace_name)


def test_architect_infers_region_from_request_text() -> None:
    workspace_name = "unit-architect-v10-region-detect"
    _clean_workspace(workspace_name)
    try:
        result = design_infrastructure(
            request=(
                "Create a private Cloud Run app connected to Cloud SQL "
                "in us-central1."
            ),
            workspace_name=workspace_name,
        )
        assert result["architecture_type"] == "private-cloud-run-cloud-sql"
        assert (
            result["dependency_graph"]["nodes"][1]["configuration"][
                "region"
            ]
            == "us-central1"
        )
    finally:
        _clean_workspace(workspace_name)


def test_architect_designs_and_assembles_full_platform() -> None:
    workspace_name = "unit-architect-v10-full"
    _clean_workspace(workspace_name)
    try:
        result = design_infrastructure(
            request=(
                "Create a private Cloud Run API connected to PostgreSQL."
            ),
            workspace_name=workspace_name,
            application="unit-architect-app",
            service_name="unit-architect-app",
        )

        assert result["deployment_performed"] is False
        assert result["architecture_type"] == "private-cloud-run-cloud-sql"
        assert result["dependency_graph"]["status"] == "success"
        assert result["assembly"]["architecture_type"] == (
            "private-cloud-run-cloud-sql"
        )

        assert result["status"] == "success"
        assert result["assembly"]["validation"]["status"] == "success"
    finally:
        _clean_workspace(workspace_name)

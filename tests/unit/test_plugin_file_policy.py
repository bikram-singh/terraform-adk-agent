"""Tests for the v0.8.2 plugin-owned file policy."""

from pathlib import Path

import pytest

from terraform_agent.intelligence.engine import (
    _validate_plugin_file_contract,
)
from terraform_agent.tools import file_tools


def test_plugin_contract_accepts_exact_match() -> None:
    _validate_plugin_file_contract(
        {"cluster.tf", "outputs.tf"},
        {"cluster.tf", "outputs.tf"},
    )


def test_plugin_contract_rejects_undeclared_file() -> None:
    with pytest.raises(ValueError, match="undeclared generated files"):
        _validate_plugin_file_contract(
            {"cluster.tf", "unexpected.tf"},
            {"cluster.tf"},
        )


def test_plugin_contract_rejects_missing_file() -> None:
    with pytest.raises(ValueError, match="declared files not generated"):
        _validate_plugin_file_contract(
            {"cluster.tf"},
            {"cluster.tf", "outputs.tf"},
        )


@pytest.mark.parametrize(
    "filename",
    [
        "../outside.tf",
        "nested/main.tf",
        "/absolute/main.tf",
        ".env",
        "script.py",
    ],
)
def test_safe_filename_rejects_unsafe_names(filename: str) -> None:
    with pytest.raises(ValueError):
        file_tools._validate_safe_filename(filename)


def test_writer_enforces_plugin_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        file_tools,
        "get_workspace_path",
        lambda _: tmp_path,
    )

    denied = file_tools.write_plugin_generated_file(
        workspace_name="unit",
        filename="node_pool.tf",
        content="terraform {}",
        allowed_filenames={"cluster.tf"},
    )

    assert denied["status"] == "error"
    assert "not declared" in denied["message"]

    allowed = file_tools.write_plugin_generated_file(
        workspace_name="unit",
        filename="node_pool.tf",
        content="terraform {}",
        allowed_filenames={"node_pool.tf"},
    )

    assert allowed["status"] == "success"
    assert (tmp_path / "node_pool.tf").exists()
"""Unit tests for the async Terraform SDK client.

Uses plain asyncio.run() inside ordinary sync test functions rather
than pytest-asyncio, since that package isn't a project dependency and
adding it just for this would be disproportionate to what's needed
here.
"""

from __future__ import annotations

import asyncio

from terraform_agent.sdk import AsyncTerraformClient


def test_run_rejects_missing_workspace() -> None:
    client = AsyncTerraformClient()

    result = asyncio.run(
        client.run("this-workspace-does-not-exist", ["validate"])
    )

    assert result["status"] == "error"
    assert "does not exist" in result["message"]


def test_run_reports_missing_terraform_executable(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "sdk-test-workspace"
    workspace.mkdir()

    monkeypatch.setattr(
        "terraform_agent.sdk.async_terraform.get_workspace_path",
        lambda name: workspace,
    )

    client = AsyncTerraformClient(
        terraform_executable="this-binary-does-not-exist-anywhere"
    )

    result = asyncio.run(client.run("sdk-test-workspace", ["validate"]))

    assert result["status"] == "error"
    assert "was not found" in result["message"]


def test_run_many_preserves_request_order(tmp_path, monkeypatch) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    def fake_get_workspace_path(name: str):
        return {"workspace-a": workspace_a, "workspace-b": workspace_b}[
            name
        ]

    monkeypatch.setattr(
        "terraform_agent.sdk.async_terraform.get_workspace_path",
        fake_get_workspace_path,
    )

    client = AsyncTerraformClient(
        terraform_executable="this-binary-does-not-exist-anywhere"
    )

    results = asyncio.run(
        client.run_many(
            [
                ("workspace-a", ["validate"]),
                ("workspace-b", ["validate"]),
            ]
        )
    )

    assert len(results) == 2
    assert results[0]["workspace_name"] == "workspace-a"
    assert results[1]["workspace_name"] == "workspace-b"


def test_validate_many_returns_dict_keyed_by_workspace(
    tmp_path, monkeypatch
) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    workspace_a.mkdir()
    workspace_b.mkdir()

    def fake_get_workspace_path(name: str):
        return {"workspace-a": workspace_a, "workspace-b": workspace_b}[
            name
        ]

    monkeypatch.setattr(
        "terraform_agent.sdk.async_terraform.get_workspace_path",
        fake_get_workspace_path,
    )

    client = AsyncTerraformClient(
        terraform_executable="this-binary-does-not-exist-anywhere"
    )

    results = asyncio.run(
        client.validate_many(["workspace-a", "workspace-b"])
    )

    assert set(results) == {"workspace-a", "workspace-b"}
    assert "initialize" in results["workspace-a"]
    assert "validate" in results["workspace-a"]
    assert results["workspace-a"]["initialize"]["status"] == "error"


def test_run_many_handles_a_mix_of_valid_and_missing_workspaces(
    tmp_path, monkeypatch
) -> None:
    """run_many dispatches every request concurrently via
    asyncio.gather; this confirms a missing workspace in one request
    doesn't prevent a valid request alongside it from completing, and
    that both results come back in request order."""

    workspace_a = tmp_path / "workspace-a"
    workspace_a.mkdir()
    missing_workspace = tmp_path / "does-not-exist-on-disk"

    def fake_get_workspace_path(name: str):
        if name == "workspace-a":
            return workspace_a
        return missing_workspace

    monkeypatch.setattr(
        "terraform_agent.sdk.async_terraform.get_workspace_path",
        fake_get_workspace_path,
    )

    client = AsyncTerraformClient(
        terraform_executable="this-binary-does-not-exist-anywhere"
    )

    results = asyncio.run(
        client.run_many(
            [
                ("workspace-a", ["validate"]),
                ("this-workspace-does-not-exist", ["validate"]),
            ]
        )
    )

    assert len(results) == 2
    assert results[0]["workspace_name"] == "workspace-a"
    assert (
        results[0]["message"] == "Terraform executable was not found. "
        "Check TERRAFORM_EXECUTABLE and PATH."
    )
    assert results[1]["status"] == "error"
    assert "does not exist" in results[1]["message"]

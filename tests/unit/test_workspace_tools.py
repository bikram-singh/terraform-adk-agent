"""Unit tests for create_workspace's empty-vs-populated distinction.

Regression coverage for a real bug found during live ADK testing: calling
create_workspace explicitly (e.g. because a user named the workspace in
their request) followed by a generator tool for the same workspace name
always failed, since every generator also calls create_workspace
internally as its own first step, and the directory already existed by
then -- even though nothing had actually been written into it yet.
"""

from __future__ import annotations

from terraform_agent.tools.workspace_tools import create_workspace


def test_create_workspace_succeeds_on_a_fresh_name(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "terraform_agent.tools.workspace_tools.get_settings",
        lambda: type("Settings", (), {"output_root": tmp_path})(),
    )

    result = create_workspace("gcs", "fresh-workspace")

    assert result["status"] == "success"
    assert (tmp_path / "fresh-workspace").is_dir()


def test_create_workspace_is_idempotent_on_an_empty_directory(
    tmp_path, monkeypatch
) -> None:
    """The real regression case: calling create_workspace twice on the
    same, still-empty workspace (as happens when a user names the
    workspace and a generator tool is called for it afterward) must
    succeed both times, not just the first."""

    monkeypatch.setattr(
        "terraform_agent.tools.workspace_tools.get_settings",
        lambda: type("Settings", (), {"output_root": tmp_path})(),
    )

    first = create_workspace("pubsub", "reused-empty-workspace")
    second = create_workspace("pubsub", "reused-empty-workspace")

    assert first["status"] == "success"
    assert second["status"] == "success"


def test_create_workspace_refuses_a_populated_directory(
    tmp_path, monkeypatch
) -> None:
    """The safety behavior that must be preserved: once a workspace
    genuinely has generated files in it, create_workspace must still
    refuse to silently reuse it."""

    monkeypatch.setattr(
        "terraform_agent.tools.workspace_tools.get_settings",
        lambda: type("Settings", (), {"output_root": tmp_path})(),
    )

    create_workspace("gcs", "populated-workspace")
    (tmp_path / "populated-workspace" / "main.tf").write_text(
        "# real generated content\n"
    )

    result = create_workspace("gcs", "populated-workspace")

    assert result["status"] == "error"
    assert "already exists" in result["message"]

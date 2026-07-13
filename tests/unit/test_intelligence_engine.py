"""Unit tests for the Version 0.4 intelligence components."""

from terraform_agent.intelligence.analyzer import analyze_gcs_request
from terraform_agent.intelligence.planner import plan_gcs_project
from terraform_agent.intelligence.registry import (
    list_registered_generators,
)


def test_analyzer_normalizes_labels() -> None:
    request = analyze_gcs_request(
        workspace_name="test-gcs-v04",
        owner="Platform Team",
    )
    assert request.owner == "platform-team"


def test_planner_creates_secure_gcs_plan() -> None:
    request = analyze_gcs_request(workspace_name="test-gcs-v04")
    plan = plan_gcs_project(request)
    assert plan.service == "gcs"
    assert "google_storage_bucket.this" in plan.resources
    assert "Public access prevention" in plan.security_controls


def test_gcs_generator_is_registered() -> None:
    assert "gcs" in list_registered_generators()

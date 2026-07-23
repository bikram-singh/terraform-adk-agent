"""Unit tests for the lightweight module registry."""

from __future__ import annotations

from terraform_agent.intelligence.module_registry import (
    COMPOSED_ARCHITECTURES,
    list_available_modules,
)
from terraform_agent.tools.registry_tools import (
    list_available_infrastructure_modules,
)


def test_list_available_modules_reports_all_eleven_generators() -> None:
    result = list_available_modules()

    assert result["status"] == "success"
    assert result["standalone_generator_count"] == 11

    service_names = {
        entry["service_name"] for entry in result["standalone_generators"]
    }
    assert service_names == {
        "artifact-registry",
        "bigquery",
        "cloud-functions",
        "cloud-run",
        "cloud-sql",
        "gcs",
        "gke",
        "iam",
        "network",
        "pubsub",
        "secret-manager",
    }


def test_list_available_modules_reports_all_generators_live_verified() -> None:
    result = list_available_modules()

    assert all(
        entry["live_verified"] for entry in result["standalone_generators"]
    )


def test_list_available_modules_reports_three_composed_architectures() -> None:
    result = list_available_modules()

    assert result["composed_architecture_count"] == 3

    architecture_types = {
        entry["architecture_type"]
        for entry in result["composed_architectures"]
    }
    assert architecture_types == {
        "private-cloud-run-cloud-sql",
        "bigquery-pubsub-cloud-functions-pipeline",
        "gke-network-iam-workload-identity-platform",
    }


def test_all_composed_architectures_are_live_verified() -> None:
    assert all(
        recipe["live_verified"] for recipe in COMPOSED_ARCHITECTURES
    )


def test_all_composed_architectures_have_a_real_assembler_tool_name() -> None:
    for recipe in COMPOSED_ARCHITECTURES:
        assert recipe["assembler_tool"]
        assert recipe["composes_generators"]


def test_tool_wrapper_matches_underlying_function() -> None:
    tool_result = list_available_infrastructure_modules()
    direct_result = list_available_modules()

    assert tool_result["standalone_generator_count"] == (
        direct_result["standalone_generator_count"]
    )
    assert tool_result["composed_architecture_count"] == (
        direct_result["composed_architecture_count"]
    )

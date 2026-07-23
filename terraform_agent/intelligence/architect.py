"""Enterprise AI Infrastructure Architect (v1.0).

Turns a single natural-language infrastructure request into a fully
assembled, locally validated Terraform project by tying together the
dependency graph (intent detection and capability resolution) and the
Project Assembler (multi-generator composition).

Three composed architecture recipes are backed by real, live-tested
assemblers: private Cloud Run + Cloud SQL, the BigQuery + Pub/Sub +
Cloud Functions event pipeline, and the GKE + Network + IAM Workload
Identity platform. Requests that describe a different or unsupported
architecture return a structured, actionable error instead of a partial
or misleading result.
"""

from __future__ import annotations

import re
from typing import Any

from terraform_agent.dependency_graph import build_dependency_graph
from terraform_agent.dependency_graph.detector import detect_architecture_type
from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)
from terraform_agent.intelligence.gke_platform_assembler import (
    assemble_gke_workload_identity_platform,
)
from terraform_agent.intelligence.pipeline_assembler import (
    assemble_bigquery_pubsub_pipeline,
)
from terraform_agent.intelligence.registry import list_registered_generators


_REGION_PATTERN = re.compile(r"\b([a-z]+-[a-z]+\d)\b")
_PUBLIC_HINTS = (
    "publicly accessible",
    "public access",
    "public internet",
    "allow unauthenticated",
    "expose to the internet",
    "expose it publicly",
    "make it public",
)
_MYSQL_HINTS = ("mysql",)

_SUPPORTED_ARCHITECTURE_RECIPES = (
    "private-cloud-run-cloud-sql",
    "bigquery-pubsub-cloud-functions-pipeline",
    "gke-network-iam-workload-identity-platform",
)


def _extract_region(request: str, default: str) -> str:
    match = _REGION_PATTERN.search(request.lower())
    return match.group(1) if match else default


def _extract_database_version(request: str, default: str) -> str:
    lowered = request.lower()
    if any(hint in lowered for hint in _MYSQL_HINTS):
        return "MYSQL_8_0"
    return default


def _extract_allow_unauthenticated(request: str, default: bool) -> bool:
    lowered = request.lower()
    if any(hint in lowered for hint in _PUBLIC_HINTS):
        return True
    return default


def design_infrastructure(
    request: str,
    workspace_name: str,
    region: str = "",
    environment: str = "dev",
    owner: str = "platform-team",
    application: str = "",
    network_name: str = "",
    subnet_cidr: str = "10.0.0.0/20",
    database_version: str = "",
    db_tier: str = "db-custom-2-7680",
    db_availability_type: str = "REGIONAL",
    database_secret_id: str = "database-password",
    service_name: str = "",
    container_image: str = "",
    container_port: int = 8080,
    allow_unauthenticated: bool = False,
) -> dict[str, Any]:
    """
    Interpret a natural-language request and assemble the architecture.

    Detects the architecture type from the request text, builds the
    dependency graph for transparency, and, when the recipe is fully
    supported, assembles and locally validates the complete multi-service
    Terraform project in the same call. Explicit keyword arguments always
    take priority over values inferred from the request text. Nothing is
    ever deployed.
    """

    architecture_type = detect_architecture_type(request)

    if architecture_type not in _SUPPORTED_ARCHITECTURE_RECIPES:
        return {
            "status": "error",
            "stage": "intent_detection",
            "request": request,
            "architecture_type": architecture_type,
            "message": (
                "No supported architecture recipe matched this request. "
                "Rephrase the request to name the services involved "
                "-- for example Cloud Run and Cloud SQL kept private, "
                "an event-driven pipeline naming Pub/Sub, Cloud "
                "Functions, or BigQuery, or a GKE cluster naming "
                "Workload Identity -- or call an individual generator "
                "directly for a single service."
            ),
            "supported_architecture_recipes": (
                _SUPPORTED_ARCHITECTURE_RECIPES
            ),
            "available_generators": list_registered_generators(),
            "generation_performed": False,
            "deployment_performed": False,
        }

    resolved_region = region or _extract_region(request, "asia-south1")
    resolved_database_version = database_version or _extract_database_version(
        request, "POSTGRES_16"
    )
    resolved_allow_unauthenticated = allow_unauthenticated or (
        _extract_allow_unauthenticated(request, False)
    )
    resolved_application = application or workspace_name.lower()

    graph = build_dependency_graph(
        request,
        resolved_region,
        resolved_database_version,
        environment,
    )

    if architecture_type == "bigquery-pubsub-cloud-functions-pipeline":
        assembly = assemble_bigquery_pubsub_pipeline(
            workspace_name=workspace_name,
            region=resolved_region,
            environment=environment,
            owner=owner,
            application=resolved_application,
        )
    elif architecture_type == "gke-network-iam-workload-identity-platform":
        assembly = assemble_gke_workload_identity_platform(
            workspace_name=workspace_name,
            region=resolved_region,
            environment=environment,
            owner=owner,
            application=resolved_application,
        )
    else:
        assembly = assemble_private_cloud_run_cloud_sql_project(
            workspace_name=workspace_name,
            region=resolved_region,
            environment=environment,
            owner=owner,
            application=resolved_application,
            network_name=network_name,
            subnet_cidr=subnet_cidr,
            database_version=resolved_database_version,
            db_tier=db_tier,
            db_availability_type=db_availability_type,
            database_secret_id=database_secret_id,
            service_name=service_name,
            container_image=container_image,
            container_port=container_port,
            allow_unauthenticated=resolved_allow_unauthenticated,
        )

    return {
        "status": assembly["status"],
        "stage": assembly.get("stage", "complete"),
        "request": request,
        "architecture_type": architecture_type,
        "dependency_graph": graph,
        "assembly": assembly,
        "deployment_performed": False,
        "message": assembly.get("message", ""),
    }

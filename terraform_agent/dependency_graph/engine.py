from __future__ import annotations
from typing import Any
from terraform_agent.dependency_graph.detector import detect_architecture_type
from terraform_agent.dependency_graph.rules import private_cloud_run_cloud_sql_graph

def build_dependency_graph(
    request: str,
    region: str = "asia-south1",
    database_engine: str = "POSTGRES_16",
    environment: str = "dev",
) -> dict[str, Any]:
    kind = detect_architecture_type(request)
    if kind == "unsupported":
        return {
            "status": "error",
            "stage": "intent_detection",
            "message": "No supported architecture recipe matched the request.",
            "generation_performed": False,
            "deployment_performed": False,
        }
    graph = private_cloud_run_cloud_sql_graph(region, database_engine, environment)
    result = graph.to_dict()
    result.update({
        "status": "success",
        "stage": "dependency_planning",
        "generation_performed": False,
        "deployment_performed": False,
        "message": "Dependency graph created. Complete generation is gated until all required generators are available.",
    })
    return result

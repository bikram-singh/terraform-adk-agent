from __future__ import annotations
from typing import Any
from terraform_agent.dependency_graph import build_dependency_graph

def plan_terraform_architecture(
    request: str,
    region: str = "asia-south1",
    database_engine: str = "POSTGRES_16",
    environment: str = "dev",
) -> dict[str, Any]:
    """Plan a multi-service Terraform architecture. Does not generate or deploy."""
    return build_dependency_graph(request, region, database_engine, environment)

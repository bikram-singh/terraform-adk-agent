from terraform_agent.dependency_graph.detector import detect_architecture_type
from terraform_agent.dependency_graph.engine import build_dependency_graph

def test_detects_private_cloud_run_cloud_sql():
    assert detect_architecture_type(
        "Create a private Cloud Run app connected to PostgreSQL."
    ) == "private-cloud-run-cloud-sql"

def test_graph_contains_required_nodes():
    result = build_dependency_graph(
        "Create a private Cloud Run application connected to Cloud SQL."
    )
    ids = {node["id"] for node in result["nodes"]}
    assert {"vpc", "subnet", "cloud-sql", "database-secret", "runtime-iam", "cloud-run"}.issubset(ids)

def test_graph_reports_all_nodes_available() -> None:
    result = build_dependency_graph(
        "Create a private Cloud Run application connected to Cloud SQL."
    )
    assert result["can_generate_complete_project"] is True
    assert result["generation_performed"] is False
    assert result["deployment_performed"] is False

def test_cloud_run_node_is_available():
    result = build_dependency_graph(
        "Create a private Cloud Run application connected to Cloud SQL."
    )
    cloud_run = next(n for n in result["nodes"] if n["id"] == "cloud-run")
    assert cloud_run["implementation_status"] == "available"

def test_unsupported_intent_is_rejected():
    result = build_dependency_graph("Create something unsupported.")
    assert result["status"] == "error"

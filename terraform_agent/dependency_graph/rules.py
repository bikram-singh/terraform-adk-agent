from terraform_agent.dependency_graph.models import ArchitectureGraph, DependencyEdge, DependencyNode

AVAILABLE = {
    "cloud-run",
    "cloud-sql",
    "gcs",
    "gke",
}

def node(node_id, service, resource_type, purpose, generator=None, config=None):
    return DependencyNode(
        id=node_id,
        service=service,
        resource_type=resource_type,
        purpose=purpose,
        implementation_status="available" if generator in AVAILABLE else "planned",
        generator_service=generator,
        configuration=config or {},
    )

def private_cloud_run_cloud_sql_graph(region: str, database_engine: str, environment: str) -> ArchitectureGraph:
    nodes = (
        node("vpc", "vpc", "google_compute_network", "Private application network."),
        node("subnet", "vpc", "google_compute_subnetwork", "Regional application subnet.", config={"region": region}),
        node("private-service-access", "networking", "google_service_networking_connection", "Private services connectivity."),
        node("serverless-vpc-connector", "networking", "google_vpc_access_connector", "Cloud Run private VPC egress.", config={"region": region}),
        node("cloud-sql", "cloud-sql", "google_sql_database_instance", "Private relational database.", generator="cloud-sql", config={"database_engine": database_engine, "region": region}),
        node("database-secret", "secret-manager", "google_secret_manager_secret", "Database credential reference."),
        node("runtime-service-account", "iam", "google_service_account", "Dedicated runtime identity."),
        node("runtime-iam", "iam", "google_project_iam_member", "Least-privilege runtime permissions."),
        node("cloud-run", "cloud-run", "google_cloud_run_v2_service", "Private serverless application.", generator="cloud-run", config={"region": region, "environment": environment}),
    )
    edges = (
        DependencyEdge("subnet", "vpc", "belongs_to"),
        DependencyEdge("private-service-access", "vpc", "connects_private_services_to"),
        DependencyEdge("serverless-vpc-connector", "subnet", "uses_subnet"),
        DependencyEdge("cloud-sql", "private-service-access", "requires"),
        DependencyEdge("runtime-iam", "runtime-service-account", "grants_roles_to"),
        DependencyEdge("runtime-iam", "cloud-sql", "grants_cloud_sql_access"),
        DependencyEdge("runtime-iam", "database-secret", "grants_secret_access"),
        DependencyEdge("cloud-run", "runtime-service-account", "runs_as"),
        DependencyEdge("cloud-run", "serverless-vpc-connector", "routes_egress_through"),
        DependencyEdge("cloud-run", "cloud-sql", "connects_to"),
        DependencyEdge("cloud-run", "database-secret", "reads"),
    )
    return ArchitectureGraph(
        architecture_type="private-cloud-run-cloud-sql",
        nodes=nodes,
        edges=edges,
        warnings=(
            "Planning only: required generators are not all available.",
            "Do not claim complete project generation until every required node is available.",
        ),
    )

"""Metadata for the Cloud SQL generator plugin."""
from terraform_agent.generators.base import ServiceMetadata

CLOUD_SQL_METADATA = ServiceMetadata(
    service_name="cloud-sql",
    display_name="Google Cloud SQL",
    provider="google",
    resources=(
        "google_sql_database_instance.this",
        "google_sql_database.application",
    ),
    supported_features=(
        "postgresql_or_mysql",
        "private_ip_only",
        "high_availability",
        "automated_backups",
        "point_in_time_recovery",
        "maintenance_window",
        "query_insights",
        "iam_database_authentication",
        "cmek_optional",
        "deletion_protection",
        "database_flags",
        "labels",
    ),
    generated_files=(
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "database.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
    ),
)

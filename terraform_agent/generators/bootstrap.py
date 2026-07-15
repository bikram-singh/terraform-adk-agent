"""Registers built-in generator plugins."""

from terraform_agent.generators.cloudrun import CloudRunGenerator
from terraform_agent.generators.cloudsql import CloudSQLGenerator
from terraform_agent.generators.gcs import GCSGenerator
from terraform_agent.generators.gke import GKEGenerator
from terraform_agent.generators.registry import generator_registry


def register_builtin_generators() -> None:
    """Register all built-in service generators exactly once."""

    registered = set(generator_registry.list_services())

    if "gcs" not in registered:
        generator_registry.register(GCSGenerator())

    if "cloud-run" not in registered:
        generator_registry.register(CloudRunGenerator())

    if "cloud-sql" not in registered:
        generator_registry.register(CloudSQLGenerator())

    if "gke" not in registered:
        generator_registry.register(GKEGenerator())

"""Registers built-in generator plugins."""

from terraform_agent.generators.artifact_registry import (
    ArtifactRegistryGenerator,
)
from terraform_agent.generators.bigquery import BigQueryGenerator
from terraform_agent.generators.cloud_functions import CloudFunctionsGenerator
from terraform_agent.generators.cloudrun import CloudRunGenerator
from terraform_agent.generators.cloudsql import CloudSQLGenerator
from terraform_agent.generators.gcs import GCSGenerator
from terraform_agent.generators.gke import GKEGenerator
from terraform_agent.generators.iam import IAMGenerator
from terraform_agent.generators.network import NetworkGenerator
from terraform_agent.generators.pubsub import PubSubGenerator
from terraform_agent.generators.registry import generator_registry
from terraform_agent.generators.secret_manager import SecretManagerGenerator


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

    if "network" not in registered:
        generator_registry.register(NetworkGenerator())

    if "secret-manager" not in registered:
        generator_registry.register(SecretManagerGenerator())

    if "iam" not in registered:
        generator_registry.register(IAMGenerator())

    if "cloud-functions" not in registered:
        generator_registry.register(CloudFunctionsGenerator())

    if "pubsub" not in registered:
        generator_registry.register(PubSubGenerator())

    if "bigquery" not in registered:
        generator_registry.register(BigQueryGenerator())

    if "artifact-registry" not in registered:
        generator_registry.register(ArtifactRegistryGenerator())

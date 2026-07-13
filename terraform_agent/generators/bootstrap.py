"""Registers built-in generator plugins."""

from terraform_agent.generators.gcs import GCSGenerator
from terraform_agent.generators.registry import generator_registry


def register_builtin_generators() -> None:
    """Register all built-in service generators exactly once."""

    if "gcs" not in generator_registry.list_services():
        generator_registry.register(GCSGenerator())

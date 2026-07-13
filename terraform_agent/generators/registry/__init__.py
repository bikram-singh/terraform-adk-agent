"""Service generator registry."""

from terraform_agent.generators.registry.registry import (
    GeneratorRegistry,
    generator_registry,
)

__all__ = ["GeneratorRegistry", "generator_registry"]

"""Multi-service Terraform generator framework."""

from terraform_agent.generators.bootstrap import register_builtin_generators
from terraform_agent.generators.registry import generator_registry

register_builtin_generators()

__all__ = ["generator_registry", "register_builtin_generators"]

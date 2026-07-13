"""Compatibility layer over the multi-service generator registry."""

from terraform_agent.generators import generator_registry


def get_generator(service: str):
    """Return a registered service generator plugin."""

    return generator_registry.get(service)


def list_registered_generators() -> tuple[str, ...]:
    """Return registered service names."""

    return generator_registry.list_services()


def list_generator_metadata() -> tuple[dict[str, object], ...]:
    """Return metadata for all registered generators."""

    return generator_registry.metadata()

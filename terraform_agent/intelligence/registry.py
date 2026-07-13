"""Generator registry for supported Terraform services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from terraform_agent.generators.gcs_generator import generate_gcs_files


Generator = Callable[..., Any]

_GENERATORS: dict[str, Generator] = {
    "gcs": generate_gcs_files,
}


def get_generator(service: str) -> Generator:
    """Return the registered generator for a service."""

    normalized = service.strip().lower().replace("_", "-")
    try:
        return _GENERATORS[normalized]
    except KeyError as exc:
        raise ValueError(
            f"No generator registered for service '{service}'. "
            f"Registered services: {sorted(_GENERATORS)}"
        ) from exc


def list_registered_generators() -> tuple[str, ...]:
    """Return registered service names."""

    return tuple(sorted(_GENERATORS))

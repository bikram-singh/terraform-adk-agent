"""Core contracts for pluggable Terraform service generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ServiceMetadata:
    """Describes one registered Terraform service plugin."""

    service_name: str
    display_name: str
    provider: str
    resources: tuple[str, ...]
    supported_features: tuple[str, ...]
    generated_files: tuple[str, ...]


@dataclass(frozen=True)
class GeneratorContext:
    """Normalized input supplied to a service generator."""

    workspace_name: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class GeneratedProject:
    """Files and metadata returned by a service generator."""

    service: str
    files: Mapping[str, str]
    metadata: ServiceMetadata
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


class TerraformGenerator(Protocol):
    """Protocol implemented by every service generator plugin."""

    @property
    def metadata(self) -> ServiceMetadata:
        """Return plugin metadata."""

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        """Generate a complete Terraform project."""

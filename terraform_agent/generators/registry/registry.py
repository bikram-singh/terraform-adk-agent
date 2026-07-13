"""Runtime registry for Terraform service plugins."""

from __future__ import annotations

from terraform_agent.generators.base import TerraformGenerator


class GeneratorRegistry:
    """Stores and resolves service generator plugins."""

    def __init__(self) -> None:
        self._generators: dict[str, TerraformGenerator] = {}

    def register(self, generator: TerraformGenerator) -> None:
        service = generator.metadata.service_name.strip().lower()
        if not service:
            raise ValueError("Generator service_name must not be empty.")
        if service in self._generators:
            raise ValueError(f"Generator already registered: {service}")
        self._generators[service] = generator

    def get(self, service: str) -> TerraformGenerator:
        normalized = service.strip().lower().replace("_", "-")
        try:
            return self._generators[normalized]
        except KeyError as exc:
            raise ValueError(
                f"No generator registered for '{service}'. "
                f"Registered services: {self.list_services()}"
            ) from exc

    def list_services(self) -> tuple[str, ...]:
        return tuple(sorted(self._generators))

    def metadata(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "service_name": item.metadata.service_name,
                "display_name": item.metadata.display_name,
                "provider": item.metadata.provider,
                "resources": item.metadata.resources,
                "supported_features": item.metadata.supported_features,
                "generated_files": item.metadata.generated_files,
            }
            for item in self._generators.values()
        )


generator_registry = GeneratorRegistry()

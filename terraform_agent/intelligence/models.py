"""Structured models used by the Terraform intelligence engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GCSRequest:
    """Normalized requirements for a secure GCS Terraform project."""

    workspace_name: str
    region: str = "asia-south1"
    environment: str = "dev"
    owner: str = "platform-team"
    application: str = "terraform-adk-agent"
    noncurrent_version_retention_days: int = 30
    versioning_enabled: bool = True
    public_access_prevention: bool = True
    uniform_bucket_level_access: bool = True
    force_destroy: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert the immutable request to a serializable dictionary."""

        return asdict(self)


@dataclass(frozen=True)
class ResourcePlan:
    """Service-neutral plan produced before Terraform rendering."""

    service: str
    workspace_name: str
    resources: tuple[str, ...]
    generated_files: tuple[str, ...]
    security_controls: tuple[str, ...]
    request: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert the plan to a serializable dictionary."""

        return asdict(self)

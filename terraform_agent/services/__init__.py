"""Application service layer."""

from terraform_agent.services.terraform_registry import (
    get_terraform_provider_version,
    get_terraform_resource_guidance,
)

__all__ = [
    "get_terraform_provider_version",
    "get_terraform_resource_guidance",
]

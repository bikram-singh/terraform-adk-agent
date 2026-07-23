"""Networking implementation of the generator contract."""

from __future__ import annotations

import re

from terraform_agent.generators.base import (
    GeneratedProject,
    GeneratorContext,
    ServiceMetadata,
)
from terraform_agent.generators.base.renderer import (
    render_default_assignment,
    render_template,
)
from terraform_agent.generators.base.validation import require_non_empty
from terraform_agent.generators.network.metadata import NETWORK_METADATA
from terraform_agent.generators.network.templates import (
    NETWORK_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PRIVATE_SERVICE_ACCESS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
    VPC_CONNECTOR_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


_CIDR_PATTERN = re.compile(
    r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$"
)
_RANGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def _validate_cidr(value: str, field_name: str) -> str:
    cleaned = require_non_empty(value, field_name)
    if not _CIDR_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a valid IPv4 CIDR range.")
    return cleaned


def _render_hcl_map(values: dict[str, str]) -> str:
    if not values:
        return "{}"

    lines = "\n".join(
        f'    "{key}" = "{value}"' for key, value in values.items()
    )
    return "{\n" + lines + "\n  }"


class NetworkGenerator:
    """Generate a private VPC networking foundation."""

    @property
    def metadata(self) -> ServiceMetadata:
        return NETWORK_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")),
            "region",
        )
        network_name = require_non_empty(
            str(values.get("network_name", "app-vpc")),
            "network_name",
        )
        subnet_name = require_non_empty(
            str(values.get("subnet_name", f"{network_name}-subnet")),
            "subnet_name",
        )
        subnet_cidr = _validate_cidr(
            str(values.get("subnet_cidr", "10.0.0.0/20")),
            "subnet_cidr",
        )

        secondary_ip_ranges = dict(values.get("secondary_ip_ranges", {}))
        for range_name, range_cidr in secondary_ip_ranges.items():
            if not _RANGE_NAME_PATTERN.fullmatch(str(range_name)):
                raise ValueError(
                    "secondary_ip_ranges keys must be lower-case names "
                    "starting with a letter."
                )
            _validate_cidr(
                str(range_cidr),
                f"secondary_ip_ranges[{range_name}]",
            )

        private_service_access_range_name = require_non_empty(
            str(
                values.get(
                    "private_service_access_range_name",
                    f"{network_name}-psa-range",
                )
            ),
            "private_service_access_range_name",
        )
        psa_prefix_length = int(
            values.get("private_service_access_prefix_length", 16)
        )
        if not 8 <= psa_prefix_length <= 24:
            raise ValueError(
                "private_service_access_prefix_length must be between "
                "8 and 24."
            )

        enable_connector = bool(
            values.get("enable_serverless_vpc_connector", True)
        )
        vpc_connector_name = require_non_empty(
            str(
                values.get(
                    "vpc_connector_name", f"{network_name}-connector"
                )
            ),
            "vpc_connector_name",
        )
        if enable_connector and len(vpc_connector_name) > 25:
            raise ValueError(
                "vpc_connector_name must be 25 characters or fewer."
            )

        vpc_connector_cidr = _validate_cidr(
            str(values.get("vpc_connector_cidr", "10.10.0.0/28")),
            "vpc_connector_cidr",
        )
        if enable_connector and not vpc_connector_cidr.endswith("/28"):
            raise ValueError(
                "vpc_connector_cidr must be a /28 range."
            )

        connector_min = int(values.get("vpc_connector_min_instances", 2))
        connector_max = int(values.get("vpc_connector_max_instances", 3))
        if enable_connector:
            if not 2 <= connector_min <= 9:
                raise ValueError(
                    "vpc_connector_min_instances must be between 2 and 9."
                )
            if not connector_min < connector_max <= 10:
                raise ValueError(
                    "vpc_connector_max_instances must be greater than "
                    "vpc_connector_min_instances and at most 10."
                )

        vpc_connector_machine_type = str(
            values.get("vpc_connector_machine_type", "e2-micro")
        )
        allowed_machine_types = {"e2-micro", "e2-standard-4", "f1-micro"}
        if (
            enable_connector
            and vpc_connector_machine_type not in allowed_machine_types
        ):
            raise ValueError(
                "vpc_connector_machine_type must be one of "
                f"{sorted(allowed_machine_types)}."
            )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "network_name": network_name,
            "subnet_name": subnet_name,
            "subnet_cidr": subnet_cidr,
            "secondary_ip_ranges": _render_hcl_map(secondary_ip_ranges),
            "secondary_ip_ranges_default_line": render_default_assignment(
                _render_hcl_map(secondary_ip_ranges)
            ),
            "private_service_access_range_name": (
                private_service_access_range_name
            ),
            "private_service_access_prefix_length": str(
                psa_prefix_length
            ),
            "enable_serverless_vpc_connector": str(
                enable_connector
            ).lower(),
            "vpc_connector_name": vpc_connector_name,
            "vpc_connector_cidr": vpc_connector_cidr,
            "vpc_connector_min_instances": str(connector_min),
            "vpc_connector_max_instances": str(connector_max),
            "vpc_connector_machine_type": vpc_connector_machine_type,
        }

        files = {
            "versions.tf": render_template(
                VERSIONS_TEMPLATE, template_values
            ),
            "providers.tf": render_template(
                PROVIDERS_TEMPLATE, template_values
            ),
            "variables.tf": render_template(
                VARIABLES_TEMPLATE, template_values
            ),
            "network.tf": render_template(
                NETWORK_TEMPLATE, template_values
            ),
            "private_service_access.tf": render_template(
                PRIVATE_SERVICE_ACCESS_TEMPLATE, template_values
            ),
            "vpc_connector.tf": render_template(
                VPC_CONNECTOR_TEMPLATE, template_values
            ),
            "outputs.tf": render_template(
                OUTPUTS_TEMPLATE, template_values
            ),
            "terraform.tfvars.example": render_template(
                TFVARS_TEMPLATE, template_values
            ),
            "README.md": render_template(
                README_TEMPLATE, template_values
            ),
        }

        return GeneratedProject(
            service=self.metadata.service_name,
            files=files,
            metadata=self.metadata,
        )

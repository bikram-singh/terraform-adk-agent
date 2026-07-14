"""GKE implementation of the multi-service generator contract."""

from __future__ import annotations

from terraform_agent.generators.base import (
    GeneratedProject,
    GeneratorContext,
    ServiceMetadata,
)
from terraform_agent.generators.base.renderer import render_template
from terraform_agent.generators.base.validation import (
    normalize_label_value,
    require_non_empty,
)
from terraform_agent.generators.gke.metadata import GKE_METADATA
from terraform_agent.generators.gke.templates import (
    ARTIFACT_REGISTRY_TEMPLATE,
    CLUSTER_TEMPLATE,
    IAM_TEMPLATE,
    NODE_POOL_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


class GKEGenerator:
    """Generate a production-oriented GKE Terraform project."""

    @property
    def metadata(self) -> ServiceMetadata:
        return GKE_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")),
            "region",
        )
        cluster_name = require_non_empty(
            str(values.get("cluster_name", "platform-gke")),
            "cluster_name",
        )

        cluster_mode = str(values.get("cluster_mode", "STANDARD")).upper()
        if cluster_mode not in {"STANDARD", "AUTOPILOT"}:
            raise ValueError(
                "cluster_mode must be STANDARD or AUTOPILOT."
            )

        environment = normalize_label_value(
            str(values.get("environment", "dev")),
            "environment",
        )
        owner = normalize_label_value(
            str(values.get("owner", "platform-team")),
            "owner",
        )
        application = normalize_label_value(
            str(values.get("application", cluster_name)),
            "application",
        )

        node_min_count = int(values.get("node_min_count", 1))
        node_max_count = int(values.get("node_max_count", 3))
        node_disk_size_gb = int(values.get("node_disk_size_gb", 100))

        if node_min_count < 0:
            raise ValueError("node_min_count must be zero or greater.")
        if node_max_count < 1:
            raise ValueError("node_max_count must be at least one.")
        if node_max_count < node_min_count:
            raise ValueError(
                "node_max_count must be greater than or equal to "
                "node_min_count."
            )
        if node_disk_size_gb < 20:
            raise ValueError("node_disk_size_gb must be at least 20.")

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "cluster_name": cluster_name,
            "cluster_mode": cluster_mode,
            "master_ipv4_cidr_block": str(
                values.get("master_ipv4_cidr_block", "172.16.0.0/28")
            ),
            "enable_private_endpoint": str(
                bool(values.get("enable_private_endpoint", True))
            ).lower(),
            "release_channel": str(
                values.get("release_channel", "REGULAR")
            ),
            "gateway_api_channel": str(
                values.get("gateway_api_channel", "CHANNEL_STANDARD")
            ),
            "enable_binary_authorization": str(
                bool(values.get("enable_binary_authorization", True))
            ).lower(),
            "deletion_protection": str(
                bool(values.get("deletion_protection", True))
            ).lower(),
            "node_machine_type": str(
                values.get("node_machine_type", "e2-standard-4")
            ),
            "node_disk_size_gb": str(node_disk_size_gb),
            "node_min_count": str(node_min_count),
            "node_max_count": str(node_max_count),
            "artifact_registry_repository_id": str(
                values.get("artifact_registry_repository_id", "gke-images")
            ),
            "environment": environment,
            "owner": owner,
            "application": application,
        }

        files = {
            "versions.tf": render_template(
                VERSIONS_TEMPLATE,
                template_values,
            ),
            "providers.tf": render_template(
                PROVIDERS_TEMPLATE,
                template_values,
            ),
            "variables.tf": render_template(
                VARIABLES_TEMPLATE,
                template_values,
            ),
            "cluster.tf": render_template(
                CLUSTER_TEMPLATE,
                template_values,
            ),
            "node_pool.tf": render_template(
                NODE_POOL_TEMPLATE,
                template_values,
            ),
            "iam.tf": render_template(
                IAM_TEMPLATE,
                template_values,
            ),
            "artifact_registry.tf": render_template(
                ARTIFACT_REGISTRY_TEMPLATE,
                template_values,
            ),
            "outputs.tf": render_template(
                OUTPUTS_TEMPLATE,
                template_values,
            ),
            "terraform.tfvars.example": render_template(
                TFVARS_TEMPLATE,
                template_values,
            ),
            "README.md": render_template(
                README_TEMPLATE,
                template_values,
            ),
        }

        return GeneratedProject(
            service=self.metadata.service_name,
            files=files,
            metadata=self.metadata,
        )

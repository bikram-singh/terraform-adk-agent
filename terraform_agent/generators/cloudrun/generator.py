"""Cloud Run implementation of the multi-service generator contract."""

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
from terraform_agent.generators.cloudrun.metadata import CLOUD_RUN_METADATA
from terraform_agent.generators.cloudrun.templates import (
    IAM_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


class CloudRunGenerator:
    """Generates secure Cloud Run v2 Terraform projects."""

    @property
    def metadata(self) -> ServiceMetadata:
        return CLOUD_RUN_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values
        region = require_non_empty(
            str(values.get("region", "asia-south1")), "region"
        )
        service_name = require_non_empty(
            str(values.get("service_name", "terraform-adk-service")),
            "service_name",
        )
        container_image = require_non_empty(
            str(values.get(
                "container_image",
                "asia-south1-docker.pkg.dev/"
                "your-project/your-repository/your-image:latest",
            )),
            "container_image",
        )
        environment = normalize_label_value(
            str(values.get("environment", "dev")), "environment"
        )
        owner = normalize_label_value(
            str(values.get("owner", "platform-team")), "owner"
        )
        application = normalize_label_value(
            str(values.get("application", service_name)), "application"
        )

        container_port = int(values.get("container_port", 8080))
        min_instances = int(values.get("min_instances", 0))
        max_instances = int(values.get("max_instances", 5))
        if not 1 <= container_port <= 65535:
            raise ValueError("container_port must be between 1 and 65535.")
        if min_instances < 0:
            raise ValueError("min_instances must be zero or greater.")
        if max_instances < 1 or max_instances < min_instances:
            raise ValueError(
                "max_instances must be at least one and not below min_instances."
            )

        ingress = str(values.get(
            "ingress", "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
        ))
        if ingress not in {
            "INGRESS_TRAFFIC_ALL",
            "INGRESS_TRAFFIC_INTERNAL_ONLY",
            "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER",
        }:
            raise ValueError(f"Unsupported ingress value: {ingress}")

        allow_unauthenticated = bool(
            values.get("allow_unauthenticated", False)
        )
        deletion_protection = bool(
            values.get("deletion_protection", True)
        )
        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "service_name": service_name,
            "container_image": container_image,
            "container_port": str(container_port),
            "cpu": str(values.get("cpu", "1")),
            "memory": str(values.get("memory", "512Mi")),
            "min_instances": str(min_instances),
            "max_instances": str(max_instances),
            "ingress": ingress,
            "allow_unauthenticated": str(
                allow_unauthenticated
            ).lower(),
            "deletion_protection": str(
                deletion_protection
            ).lower(),
            "environment": environment,
            "owner": owner,
            "application": application,
        }
        files = {
            "versions.tf": render_template(VERSIONS_TEMPLATE, template_values),
            "providers.tf": render_template(PROVIDERS_TEMPLATE, template_values),
            "variables.tf": render_template(VARIABLES_TEMPLATE, template_values),
            "main.tf": render_template(MAIN_TEMPLATE, template_values),
            "iam.tf": render_template(IAM_TEMPLATE, template_values),
            "outputs.tf": render_template(OUTPUTS_TEMPLATE, template_values),
            "terraform.tfvars.example": render_template(
                TFVARS_TEMPLATE, template_values
            ),
            "README.md": render_template(README_TEMPLATE, template_values),
        }
        diagnostics = (
            ("Public invocation was explicitly enabled with allUsers.",)
            if allow_unauthenticated
            else ()
        )
        return GeneratedProject(
            service=self.metadata.service_name,
            files=files,
            metadata=self.metadata,
            diagnostics=diagnostics,
        )

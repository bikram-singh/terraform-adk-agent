"""Cloud Functions (2nd gen) implementation of the generator contract."""

from __future__ import annotations

import re

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
from terraform_agent.generators.cloud_functions.metadata import (
    CLOUD_FUNCTIONS_METADATA,
)
from terraform_agent.generators.cloud_functions.templates import (
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


_FUNCTION_NAME_PATTERN = re.compile(r"^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$")
_INGRESS_SETTINGS = {
    "ALLOW_ALL",
    "ALLOW_INTERNAL_ONLY",
    "ALLOW_INTERNAL_AND_GCLB",
}


class CloudFunctionsGenerator:
    """Generate a private-by-default HTTP-triggered Cloud Function."""

    @property
    def metadata(self) -> ServiceMetadata:
        return CLOUD_FUNCTIONS_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")), "region"
        )
        function_name = require_non_empty(
            str(values.get("function_name", "terraform-adk-function")),
            "function_name",
        )
        if not _FUNCTION_NAME_PATTERN.fullmatch(function_name):
            raise ValueError(
                "function_name must use lower-case letters, numbers, "
                "and hyphens, and be 63 characters or fewer."
            )

        source_bucket_name = require_non_empty(
            str(
                values.get(
                    "source_bucket_name", f"{function_name}-source"
                )
            ),
            "source_bucket_name",
        )

        runtime = require_non_empty(
            str(values.get("runtime", "python312")), "runtime"
        )
        entry_point = require_non_empty(
            str(values.get("entry_point", "main")), "entry_point"
        )

        environment = normalize_label_value(
            str(values.get("environment", "dev")), "environment"
        )
        owner = normalize_label_value(
            str(values.get("owner", "platform-team")), "owner"
        )
        application = normalize_label_value(
            str(values.get("application", function_name)), "application"
        )

        timeout_seconds = int(values.get("timeout_seconds", 60))
        min_instance_count = int(values.get("min_instance_count", 0))
        max_instance_count = int(values.get("max_instance_count", 10))

        if not 1 <= timeout_seconds <= 3600:
            raise ValueError(
                "timeout_seconds must be between 1 and 3600."
            )
        if min_instance_count < 0:
            raise ValueError(
                "min_instance_count must be zero or greater."
            )
        if max_instance_count < 1 or max_instance_count < min_instance_count:
            raise ValueError(
                "max_instance_count must be at least one and not below "
                "min_instance_count."
            )

        ingress_settings = str(
            values.get("ingress_settings", "ALLOW_INTERNAL_ONLY")
        )
        if ingress_settings not in _INGRESS_SETTINGS:
            raise ValueError(
                f"Unsupported ingress_settings value: {ingress_settings}"
            )

        allow_unauthenticated = bool(
            values.get("allow_unauthenticated", False)
        )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "function_name": function_name,
            "source_bucket_name": source_bucket_name,
            "runtime": runtime,
            "entry_point": entry_point,
            "available_memory": str(
                values.get("available_memory", "256M")
            ),
            "available_cpu": str(values.get("available_cpu", "1")),
            "timeout_seconds": str(timeout_seconds),
            "min_instance_count": str(min_instance_count),
            "max_instance_count": str(max_instance_count),
            "ingress_settings": ingress_settings,
            "allow_unauthenticated": str(
                allow_unauthenticated
            ).lower(),
            "environment": environment,
            "owner": owner,
            "application": application,
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
            "main.tf": render_template(MAIN_TEMPLATE, template_values),
            "iam.tf": render_template(IAM_TEMPLATE, template_values),
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

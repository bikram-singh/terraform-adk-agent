"""IAM implementation of the generator contract."""

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
    validate_iam_member,
)
from terraform_agent.generators.iam.metadata import IAM_METADATA
from terraform_agent.generators.iam.templates import (
    IMPERSONATION_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROJECT_IAM_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


_SERVICE_ACCOUNT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_ROLE_PATTERN = re.compile(
    r"^(roles/|projects/[^/]+/roles/|organizations/[^/]+/roles/)"
    r"[A-Za-z0-9_.]+$"
)
_DISALLOWED_ROLES = {"roles/owner", "roles/editor"}
_ALLOWED_IMPERSONATION_ROLES = {
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountTokenCreator",
    "roles/iam.workloadIdentityUser",
}


def _render_hcl_list(values: list[str]) -> str:
    if not values:
        return "[]"

    lines = ",\n".join(f'    "{value}"' for value in values)
    return "[\n" + lines + "\n  ]"


class IAMGenerator:
    """Generate a dedicated runtime service account and role bindings."""

    @property
    def metadata(self) -> ServiceMetadata:
        return IAM_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")),
            "region",
        )

        service_account_id = require_non_empty(
            str(values.get("service_account_id", "")),
            "service_account_id",
        )
        if not _SERVICE_ACCOUNT_ID_PATTERN.fullmatch(service_account_id):
            raise ValueError(
                "service_account_id must be 6-30 characters: lower-case "
                "letters, digits, or hyphens, starting with a letter."
            )

        service_account_display_name = str(
            values.get(
                "service_account_display_name",
                f"{service_account_id} runtime identity",
            )
        ).strip()

        project_roles = [
            str(item).strip() for item in values.get("project_roles", [])
        ]
        if not project_roles:
            raise ValueError(
                "project_roles must contain at least one entry."
            )
        if len(project_roles) != len(set(project_roles)):
            raise ValueError("project_roles must not contain duplicates.")

        for role in project_roles:
            if role in _DISALLOWED_ROLES:
                raise ValueError(
                    f"project_roles must not include '{role}'. Grant "
                    "least-privilege predefined or custom roles instead."
                )
            if not _ROLE_PATTERN.fullmatch(role):
                raise ValueError(f"Invalid project role '{role}'.")

        impersonators = [
            validate_iam_member(str(item), "impersonators")
            for item in values.get("impersonators", [])
        ]
        if len(impersonators) != len(set(impersonators)):
            raise ValueError("impersonators must not contain duplicates.")

        impersonation_role = str(
            values.get("impersonation_role", "roles/iam.serviceAccountUser")
        )
        if impersonation_role not in _ALLOWED_IMPERSONATION_ROLES:
            raise ValueError(
                f"Unsupported impersonation_role: {impersonation_role}. "
                f"Must be one of {sorted(_ALLOWED_IMPERSONATION_ROLES)}."
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
            str(values.get("application", "terraform-adk-agent")),
            "application",
        )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "service_account_id": service_account_id,
            "service_account_display_name": service_account_display_name,
            "project_roles": _render_hcl_list(project_roles),
            "impersonators": _render_hcl_list(impersonators),
            "impersonation_role": impersonation_role,
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
            "project_iam.tf": render_template(
                PROJECT_IAM_TEMPLATE, template_values
            ),
            "impersonation.tf": render_template(
                IMPERSONATION_TEMPLATE, template_values
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
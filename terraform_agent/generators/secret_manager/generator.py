"""Secret Manager implementation of the generator contract."""

from __future__ import annotations

import re

from terraform_agent.generators.base import (
    GeneratedProject,
    GeneratorContext,
    ServiceMetadata,
)
from terraform_agent.generators.base.renderer import (
    render_default_assignment,
    render_hcl_string_list,
    render_template,
)
from terraform_agent.generators.base.validation import (
    normalize_label_value,
    validate_iam_member,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER
from terraform_agent.generators.secret_manager.metadata import (
    SECRET_MANAGER_METADATA,
)
from terraform_agent.generators.secret_manager.templates import (
    IAM_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)


_SECRET_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,255}$")
_REGION_PATTERN = re.compile(r"^[a-z]+-[a-z]+\d+$")


class SecretManagerGenerator:
    """Generate Secret Manager containers with least-privilege access."""

    @property
    def metadata(self) -> ServiceMetadata:
        return SECRET_MANAGER_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = str(values.get("region", "asia-south1")).strip()
        if not region:
            raise ValueError("region must not be empty.")

        secret_ids = [
            str(item).strip() for item in values.get("secret_ids", [])
        ]
        if not secret_ids:
            raise ValueError("secret_ids must contain at least one entry.")

        if len(secret_ids) != len(set(secret_ids)):
            raise ValueError("secret_ids must not contain duplicates.")

        for secret_id in secret_ids:
            if not _SECRET_ID_PATTERN.fullmatch(secret_id):
                raise ValueError(
                    f"Invalid secret_id '{secret_id}'. Secret IDs may "
                    "only contain letters, numbers, hyphens, or "
                    "underscores, and must be 1-255 characters."
                )

        replication_locations = [
            str(item).strip()
            for item in values.get("replication_locations", [])
        ]
        for location in replication_locations:
            if not _REGION_PATTERN.fullmatch(location):
                raise ValueError(
                    f"Invalid replication location '{location}'."
                )
        if len(replication_locations) != len(set(replication_locations)):
            raise ValueError(
                "replication_locations must not contain duplicates."
            )

        accessor_members = [
            validate_iam_member(str(item), "accessor_members")
            for item in values.get("accessor_members", [])
        ]

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

        rendered_secret_ids = render_hcl_string_list(secret_ids)
        rendered_replication_locations = render_hcl_string_list(
            replication_locations
        )
        rendered_accessor_members = render_hcl_string_list(
            accessor_members
        )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "secret_ids": rendered_secret_ids,
            "secret_ids_default_line": render_default_assignment(
                rendered_secret_ids
            ),
            "replication_locations": rendered_replication_locations,
            "replication_locations_default_line": (
                render_default_assignment(
                    rendered_replication_locations
                )
            ),
            "accessor_members": rendered_accessor_members,
            "accessor_members_default_line": render_default_assignment(
                rendered_accessor_members
            ),
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

        return GeneratedProject(
            service=self.metadata.service_name,
            files=files,
            metadata=self.metadata,
        )

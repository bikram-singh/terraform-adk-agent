"""Artifact Registry implementation of the generator contract."""

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
    require_non_empty,
    validate_iam_member,
)
from terraform_agent.generators.artifact_registry.metadata import (
    ARTIFACT_REGISTRY_METADATA,
)
from terraform_agent.generators.artifact_registry.templates import (
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


_REPOSITORY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_ALLOWED_FORMATS = frozenset(
    {"DOCKER", "MAVEN", "NPM", "PYTHON", "APT", "YUM", "GENERIC"}
)


class ArtifactRegistryGenerator:
    """Generate an Artifact Registry repository with least-privilege
    reader/writer IAM bindings."""

    @property
    def metadata(self) -> ServiceMetadata:
        return ARTIFACT_REGISTRY_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")), "region"
        )

        repository_id = require_non_empty(
            str(values.get("repository_id", "")), "repository_id"
        )
        if not _REPOSITORY_ID_PATTERN.fullmatch(repository_id):
            raise ValueError(
                f"Invalid repository_id '{repository_id}'. Must be "
                "1-63 characters: lower-case letters, digits, "
                "hyphens, or underscores, starting with a letter."
            )

        format_value = str(values.get("format", "DOCKER")).strip().upper()
        if format_value not in _ALLOWED_FORMATS:
            raise ValueError(
                f"Unsupported format '{format_value}'. Must be one of "
                f"{sorted(_ALLOWED_FORMATS)}."
            )

        description = str(
            values.get("description", f"{repository_id} repository")
        ).strip()

        reader_members = [
            validate_iam_member(str(item), "reader_members")
            for item in values.get("reader_members", [])
        ]
        writer_members = [
            validate_iam_member(str(item), "writer_members")
            for item in values.get("writer_members", [])
        ]

        enable_cleanup_policy = bool(
            values.get("enable_cleanup_policy", True)
        )

        cleanup_policy_keep_count = int(
            values.get("cleanup_policy_keep_count", 10)
        )
        if cleanup_policy_keep_count < 1:
            raise ValueError(
                "cleanup_policy_keep_count must be at least 1."
            )

        # Safe by default: a cleanup policy's real deletions should be
        # reviewed in a plan before ever actually removing anything.
        cleanup_policy_dry_run = bool(
            values.get("cleanup_policy_dry_run", True)
        )

        environment = normalize_label_value(
            str(values.get("environment", "dev")), "environment"
        )
        owner = normalize_label_value(
            str(values.get("owner", "platform-team")), "owner"
        )
        application = normalize_label_value(
            str(values.get("application", "terraform-adk-agent")),
            "application",
        )

        rendered_reader_members = render_hcl_string_list(reader_members)
        rendered_writer_members = render_hcl_string_list(writer_members)

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "repository_id": repository_id,
            "format": format_value,
            "description": description,
            "reader_members": rendered_reader_members,
            "reader_members_default_line": render_default_assignment(
                rendered_reader_members
            ),
            "writer_members": rendered_writer_members,
            "writer_members_default_line": render_default_assignment(
                rendered_writer_members
            ),
            "enable_cleanup_policy": str(enable_cleanup_policy).lower(),
            "cleanup_policy_keep_count": cleanup_policy_keep_count,
            "cleanup_policy_dry_run": str(
                cleanup_policy_dry_run
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

        return GeneratedProject(
            service=self.metadata.service_name,
            files=files,
            metadata=self.metadata,
        )

"""GCS implementation of the multi-service generator contract."""

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
from terraform_agent.generators.gcs.metadata import GCS_METADATA
from terraform_agent.generators.gcs.templates import (
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


_ALLOWED_STORAGE_CLASSES = {
    "STANDARD",
    "NEARLINE",
    "COLDLINE",
    "ARCHIVE",
}


class GCSGenerator:
    """Generate secure Google Cloud Storage Terraform projects."""

    @property
    def metadata(self) -> ServiceMetadata:
        """Return GCS generator metadata."""
        return GCS_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        """Generate a complete secure GCS Terraform project."""

        values = context.values

        project_id = require_non_empty(
            str(values.get("project_id", "")),
            "project_id",
        )

        bucket_name = require_non_empty(
            str(values.get("bucket_name", "")),
            "bucket_name",
        )

        location = require_non_empty(
            str(values.get("location") or values.get("region", "")),
            "location",
        )

        storage_class = require_non_empty(
            str(values.get("storage_class", "STANDARD")),
            "storage_class",
        ).upper()

        if storage_class not in _ALLOWED_STORAGE_CLASSES:
            allowed = ", ".join(sorted(_ALLOWED_STORAGE_CLASSES))
            raise ValueError(
                f"storage_class must be one of: {allowed}."
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

        retention_days = int(
            values.get("noncurrent_version_retention_days", 30)
        )

        if retention_days < 1:
            raise ValueError(
                "noncurrent_version_retention_days must be at least 1."
            )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "project_id": project_id,
            "bucket_name": bucket_name,
            "location": location,
            "storage_class": storage_class,
            "environment": environment,
            "owner": owner,
            "application": application,
            "retention_days": str(retention_days),
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
            "main.tf": render_template(
                MAIN_TEMPLATE,
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
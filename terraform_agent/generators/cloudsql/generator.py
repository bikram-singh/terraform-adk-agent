"""Cloud SQL implementation of the generator contract."""

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
from terraform_agent.generators.cloudsql.metadata import CLOUD_SQL_METADATA
from terraform_agent.generators.cloudsql.templates import (
    DATABASE_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


class CloudSQLGenerator:
    """Generate a private production-oriented Cloud SQL project."""

    @property
    def metadata(self) -> ServiceMetadata:
        return CLOUD_SQL_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")),
            "region",
        )
        instance_name = require_non_empty(
            str(values.get("instance_name", "application-db")),
            "instance_name",
        )
        database_version = require_non_empty(
            str(values.get("database_version", "POSTGRES_16")).upper(),
            "database_version",
        )

        if not (
            database_version.startswith("POSTGRES_")
            or database_version.startswith("MYSQL_")
        ):
            raise ValueError(
                "database_version must be PostgreSQL or MySQL."
            )

        availability_type = str(
            values.get("availability_type", "REGIONAL")
        ).upper()
        if availability_type not in {"ZONAL", "REGIONAL"}:
            raise ValueError(
                "availability_type must be ZONAL or REGIONAL."
            )

        disk_size_gb = int(values.get("disk_size_gb", 100))
        backup_count = int(values.get("backup_retained_count", 14))
        log_days = int(values.get("transaction_log_retention_days", 7))

        if disk_size_gb < 10:
            raise ValueError("disk_size_gb must be at least 10.")
        if not 1 <= backup_count <= 365:
            raise ValueError(
                "backup_retained_count must be between 1 and 365."
            )
        if not 1 <= log_days <= 7:
            raise ValueError(
                "transaction_log_retention_days must be between 1 and 7."
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
            str(values.get("application", instance_name)),
            "application",
        )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "instance_name": instance_name,
            "database_version": database_version,
            "tier": str(values.get("tier", "db-custom-2-7680")),
            "availability_type": availability_type,
            "disk_size_gb": str(disk_size_gb),
            "enable_iam_database_authentication": str(
                bool(
                    values.get(
                        "enable_iam_database_authentication",
                        True,
                    )
                )
            ).lower(),
            "backup_start_time": str(
                values.get("backup_start_time", "02:00")
            ),
            "backup_retained_count": str(backup_count),
            "transaction_log_retention_days": str(log_days),
            "maintenance_day": str(values.get("maintenance_day", 7)),
            "maintenance_hour": str(values.get("maintenance_hour", 3)),
            "deletion_protection": str(
                bool(values.get("deletion_protection", True))
            ).lower(),
            "database_name": str(
                values.get("database_name", "application")
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
            "main.tf": render_template(
                MAIN_TEMPLATE, template_values
            ),
            "database.tf": render_template(
                DATABASE_TEMPLATE, template_values
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

"""BigQuery implementation of the generator contract."""

from __future__ import annotations

import json
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
from terraform_agent.generators.bigquery.metadata import BIGQUERY_METADATA
from terraform_agent.generators.bigquery.templates import (
    IAM_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    TABLES_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER


_DATASET_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_TABLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,1024}$")


def _render_hcl_list(values: list[str]) -> str:
    if not values:
        return "[]"

    lines = ",\n".join(f'    "{value}"' for value in values)
    return "[\n" + lines + "\n  ]"


def _render_hcl_tables(tables: dict[str, dict]) -> str:
    if not tables:
        return "{}"

    entries = []
    for table_id, config in tables.items():
        entries.append(
            f'    "{table_id}" = {{\n'
            f'      schema_json        = {json.dumps(config["schema_json"])}\n'
            f'      description        = {json.dumps(config["description"])}\n'
            "      partitioning_field = "
            f'{json.dumps(config["partitioning_field"])}\n'
            "    }"
        )

    return "{\n" + "\n".join(entries) + "\n  }"


class BigQueryGenerator:
    """Generate a BigQuery dataset and tables with least-privilege IAM."""

    @property
    def metadata(self) -> ServiceMetadata:
        return BIGQUERY_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = require_non_empty(
            str(values.get("region", "asia-south1")), "region"
        )
        dataset_id = require_non_empty(
            str(values.get("dataset_id", "analytics")), "dataset_id"
        )
        if not _DATASET_ID_PATTERN.fullmatch(dataset_id):
            raise ValueError(
                "dataset_id must contain only letters, numbers, or "
                "underscores, and start with a letter or underscore."
            )

        location = require_non_empty(
            str(values.get("location", region)), "location"
        )

        default_table_expiration_ms = values.get(
            "default_table_expiration_ms"
        )
        if default_table_expiration_ms is not None:
            default_table_expiration_ms = int(default_table_expiration_ms)
            if default_table_expiration_ms <= 0:
                raise ValueError(
                    "default_table_expiration_ms must be greater than "
                    "zero when provided."
                )

        deletion_protection = bool(
            values.get("deletion_protection", True)
        )

        raw_tables = values.get(
            "tables",
            {
                "events": {
                    "schema_json": json.dumps(
                        [
                            {
                                "name": "id",
                                "type": "STRING",
                                "mode": "REQUIRED",
                            },
                            {
                                "name": "created_at",
                                "type": "TIMESTAMP",
                                "mode": "REQUIRED",
                            },
                        ]
                    ),
                    "description": (
                        "Default sample table. Replace with your own "
                        "schema."
                    ),
                    "partitioning_field": "created_at",
                }
            },
        )
        if not raw_tables:
            raise ValueError("tables must contain at least one entry.")

        tables: dict[str, dict] = {}
        for table_id, config in raw_tables.items():
            cleaned_table_id = str(table_id).strip()
            if not _TABLE_ID_PATTERN.fullmatch(cleaned_table_id):
                raise ValueError(f"Invalid table_id '{cleaned_table_id}'.")

            schema_json = str(config.get("schema_json", "[]"))
            try:
                parsed_schema = json.loads(schema_json)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Table '{cleaned_table_id}' schema_json must be "
                    "valid JSON."
                ) from exc
            if not isinstance(parsed_schema, list):
                raise ValueError(
                    f"Table '{cleaned_table_id}' schema_json must be a "
                    "JSON array of field definitions."
                )

            field_names = {
                field.get("name")
                for field in parsed_schema
                if isinstance(field, dict)
            }

            partitioning_field = str(
                config.get("partitioning_field", "")
            ).strip()
            if (
                partitioning_field
                and partitioning_field not in field_names
            ):
                raise ValueError(
                    f"Table '{cleaned_table_id}' partitioning_field "
                    f"'{partitioning_field}' must match a field name in "
                    "schema_json."
                )

            tables[cleaned_table_id] = {
                "schema_json": schema_json,
                "description": str(config.get("description", "")),
                "partitioning_field": partitioning_field,
            }

        reader_members = [
            validate_iam_member(str(item), "reader_members")
            for item in values.get("reader_members", [])
        ]
        editor_members = [
            validate_iam_member(str(item), "editor_members")
            for item in values.get("editor_members", [])
        ]

        environment = normalize_label_value(
            str(values.get("environment", "dev")), "environment"
        )
        owner = normalize_label_value(
            str(values.get("owner", "platform-team")), "owner"
        )
        application = normalize_label_value(
            str(values.get("application", dataset_id)), "application"
        )

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "dataset_id": dataset_id,
            "location": location,
            "default_table_expiration_ms": (
                "null"
                if default_table_expiration_ms is None
                else str(default_table_expiration_ms)
            ),
            "deletion_protection": str(deletion_protection).lower(),
            "tables": _render_hcl_tables(tables),
            "reader_members": _render_hcl_list(reader_members),
            "editor_members": _render_hcl_list(editor_members),
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
            "tables.tf": render_template(
                TABLES_TEMPLATE, template_values
            ),
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

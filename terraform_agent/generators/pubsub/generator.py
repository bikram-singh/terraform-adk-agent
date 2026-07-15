"""Pub/Sub implementation of the generator contract."""

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
    validate_iam_member,
)
from terraform_agent.generators.providers import GOOGLE_PROVIDER
from terraform_agent.generators.pubsub.metadata import PUBSUB_METADATA
from terraform_agent.generators.pubsub.templates import (
    IAM_TEMPLATE,
    MAIN_TEMPLATE,
    OUTPUTS_TEMPLATE,
    PROVIDERS_TEMPLATE,
    README_TEMPLATE,
    SUBSCRIPTIONS_TEMPLATE,
    TFVARS_TEMPLATE,
    VARIABLES_TEMPLATE,
    VERSIONS_TEMPLATE,
)


_TOPIC_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,254}$")
_SUBSCRIPTION_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,254}$")
_DURATION_PATTERN = re.compile(r"^\d+s$")


def _render_hcl_list(values: list[str]) -> str:
    if not values:
        return "[]"

    lines = ",\n".join(f'    "{value}"' for value in values)
    return "[\n" + lines + "\n  ]"


def _render_hcl_subscriptions(subscriptions: dict[str, dict]) -> str:
    if not subscriptions:
        return "{}"

    entries = []
    for name, config in subscriptions.items():
        entries.append(
            f'    "{name}" = {{\n'
            f'      topic                       = "{config["topic"]}"\n'
            "      ack_deadline_seconds        = "
            f'{config["ack_deadline_seconds"]}\n'
            "      message_retention_duration  = "
            f'"{config["message_retention_duration"]}"\n'
            "      enable_dead_letter          = "
            f'{str(config["enable_dead_letter"]).lower()}\n'
            "      max_delivery_attempts       = "
            f'{config["max_delivery_attempts"]}\n'
            "    }"
        )

    return "{\n" + "\n".join(entries) + "\n  }"


class PubSubGenerator:
    """Generate Pub/Sub topics and subscriptions with least-privilege IAM."""

    @property
    def metadata(self) -> ServiceMetadata:
        return PUBSUB_METADATA

    def generate(self, context: GeneratorContext) -> GeneratedProject:
        values = context.values

        region = str(values.get("region", "asia-south1")).strip()
        if not region:
            raise ValueError("region must not be empty.")

        topics = [str(item).strip() for item in values.get("topics", [])]
        if not topics:
            raise ValueError("topics must contain at least one entry.")
        if len(topics) != len(set(topics)):
            raise ValueError("topics must not contain duplicates.")
        for topic in topics:
            if not _TOPIC_NAME_PATTERN.fullmatch(topic):
                raise ValueError(f"Invalid topic name '{topic}'.")

        raw_subscriptions = values.get("subscriptions", {})
        subscriptions: dict[str, dict] = {}
        for name, config in raw_subscriptions.items():
            cleaned_name = str(name).strip()
            if not _SUBSCRIPTION_NAME_PATTERN.fullmatch(cleaned_name):
                raise ValueError(
                    f"Invalid subscription name '{cleaned_name}'."
                )

            topic = str(config.get("topic", "")).strip()
            if topic not in topics:
                raise ValueError(
                    f"Subscription '{cleaned_name}' references topic "
                    f"'{topic}', which is not declared in topics."
                )

            ack_deadline_seconds = int(
                config.get("ack_deadline_seconds", 10)
            )
            if not 10 <= ack_deadline_seconds <= 600:
                raise ValueError(
                    f"Subscription '{cleaned_name}' ack_deadline_seconds "
                    "must be between 10 and 600."
                )

            message_retention_duration = str(
                config.get("message_retention_duration", "604800s")
            )
            if not _DURATION_PATTERN.fullmatch(message_retention_duration):
                raise ValueError(
                    f"Subscription '{cleaned_name}' "
                    "message_retention_duration must look like '604800s'."
                )

            enable_dead_letter = bool(
                config.get("enable_dead_letter", False)
            )
            max_delivery_attempts = int(
                config.get("max_delivery_attempts", 5)
            )
            if not 5 <= max_delivery_attempts <= 100:
                raise ValueError(
                    f"Subscription '{cleaned_name}' max_delivery_attempts "
                    "must be between 5 and 100."
                )

            subscriptions[cleaned_name] = {
                "topic": topic,
                "ack_deadline_seconds": ack_deadline_seconds,
                "message_retention_duration": message_retention_duration,
                "enable_dead_letter": enable_dead_letter,
                "max_delivery_attempts": max_delivery_attempts,
            }

        publisher_members = [
            validate_iam_member(str(item), "publisher_members")
            for item in values.get("publisher_members", [])
        ]
        subscriber_members = [
            validate_iam_member(str(item), "subscriber_members")
            for item in values.get("subscriber_members", [])
        ]

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

        template_values = {
            "terraform_version": GOOGLE_PROVIDER[
                "terraform_version_constraint"
            ],
            "provider_source": GOOGLE_PROVIDER["source"],
            "provider_version": GOOGLE_PROVIDER["version_constraint"],
            "region": region,
            "topics": _render_hcl_list(topics),
            "subscriptions": _render_hcl_subscriptions(subscriptions),
            "publisher_members": _render_hcl_list(publisher_members),
            "subscriber_members": _render_hcl_list(subscriber_members),
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
            "subscriptions.tf": render_template(
                SUBSCRIPTIONS_TEMPLATE, template_values
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

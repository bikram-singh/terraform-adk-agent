"""Live end-to-end test for a generated Pub/Sub Terraform project.

This test creates a real Pub/Sub topic and a real durable subscription,
verifies them against live Terraform/GCP state, and always destroys them
during cleanup -- even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by the existing GCS, Secret Manager, and IAM live tests.

Notable difference from the other generators: `main.tf` includes a
`data "google_project" "this"` data source, used to build the Pub/Sub
service agent's member string for dead-letter IAM bindings. Terraform reads
data sources during `plan` regardless of `-refresh`, so this generator has
always required real, authenticated GCP access even for a "safe" plan-only
run -- this live test simply goes one step further and also applies and
destroys real messaging resources. `data.google_project.this` will appear
in `terraform state list` output alongside the managed resources; the
assertions below account for that explicitly rather than assuming an
empty/managed-only state.

Dead-letter queues and IAM member bindings are intentionally left disabled
for this first live pass (fewer moving parts, faster teardown); they're a
reasonable follow-up if deeper live coverage is wanted later.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.pubsub.generator import PubSubGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "pubsub-live-e2e-test"

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_topic_name() -> str:
    """Create a unique, valid Pub/Sub topic name for this test run."""

    timestamp_suffix = format(int(time.time()) % 100000, "x")
    random_suffix = uuid4().hex[:6]

    return f"pubsub-e2e-{timestamp_suffix}{random_suffix}"


def replace_tfvars_string_value(
    content: str,
    variable_name: str,
    value: str,
) -> str:
    """Replace a quoted string value in Terraform tfvars content."""

    pattern = re.compile(
        rf'(?m)^(\s*{re.escape(variable_name)}\s*=\s*)"[^"]*"\s*$'
    )

    updated_content, replacement_count = pattern.subn(
        rf'\1"{value}"',
        content,
        count=1,
    )

    if replacement_count != 1:
        raise ValueError(
            f"Unable to replace Terraform variable: {variable_name}"
        )

    return updated_content


@pytest.fixture(scope="module")
def live_e2e_enabled() -> None:
    """Skip live infrastructure tests unless explicitly enabled."""

    if not environment_flag_enabled("TERRAFORM_E2E_LIVE"):
        pytest.skip(
            "Live Terraform E2E testing is disabled. "
            "Set TERRAFORM_E2E_LIVE=true to enable it."
        )

    if not environment_flag_enabled("TERRAFORM_ALLOW_APPLY"):
        pytest.skip(
            "Terraform apply is disabled. "
            "Set TERRAFORM_ALLOW_APPLY=true to enable live testing."
        )


@pytest.fixture(scope="module")
def live_project_id(live_e2e_enabled: None) -> str:
    """Return the real GCP project ID used for live Pub/Sub testing."""

    project_id = (
        os.getenv("PUBSUB_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Pub/Sub test. "
            "Set PUBSUB_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_topic_name() -> str:
    """Return a unique topic name for this test execution."""

    return create_unique_topic_name()


@pytest.fixture(scope="module")
def live_subscription_name(live_topic_name: str) -> str:
    """Return a unique subscription name derived from the topic name."""

    return f"{live_topic_name}-sub"


@pytest.fixture(scope="module")
def pubsub_live_workspace(
    repository_root: Path,
    live_topic_name: str,
    live_subscription_name: str,
) -> Path:
    """Generate a fresh Pub/Sub workspace with unique resource names."""

    generator = PubSubGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "topics": [live_topic_name],
                "subscriptions": {
                    live_subscription_name: {"topic": live_topic_name},
                },
                "publisher_members": [],
                "subscriber_members": [],
                "environment": "dev",
                "owner": "platform-team",
                "application": "pubsub-live-e2e",
            },
        )
    )

    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    for name, content in project.files.items():
        (workspace / name).write_text(content, encoding="utf-8")

    return workspace


@pytest.fixture(scope="module")
def live_var_file(
    pubsub_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = pubsub_live_workspace / "terraform.tfvars.example"
    live_file = pubsub_live_workspace / "terraform.live.tfvars"

    if not example_file.exists():
        pytest.fail(
            f"Terraform variable example does not exist: {example_file}"
        )

    example_content = example_file.read_text(encoding="utf-8")

    live_content = replace_tfvars_string_value(
        content=example_content,
        variable_name="project_id",
        value=live_project_id,
    )

    live_file.write_text(live_content, encoding="utf-8")

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def pubsub_live_runner(
    pubsub_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live Pub/Sub workspace."""

    return terraform_runner_factory(pubsub_live_workspace)


def test_pubsub_live_apply_verify_and_destroy(
    pubsub_live_runner: TerraformRunner,
    live_var_file: Path,
    live_topic_name: str,
    live_subscription_name: str,
) -> None:
    """Deploy, verify, and destroy a real Pub/Sub topic and subscription."""

    topic_address = f'google_pubsub_topic.this["{live_topic_name}"]'
    subscription_address = (
        f'google_pubsub_subscription.this["{live_subscription_name}"]'
    )

    plan_file = pubsub_live_runner.working_directory / "pubsub-live-e2e.tfplan"

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        init_result = pubsub_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = pubsub_live_runner.validate()
        assert validate_result.succeeded

        plan_result = pubsub_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = pubsub_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert topic_address in resource_addresses
        assert subscription_address in resource_addresses

        topic_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == topic_address
        ]

        assert len(topic_changes) == 1
        assert (
            topic_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        apply_result = pubsub_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(pubsub_live_runner.state_list())

        assert topic_address in state_resources
        assert subscription_address in state_resources
        # `data.google_project.this` is also tracked in state since
        # main.tf reads it to build the Pub/Sub service agent member.
        assert state_resources == {
            topic_address,
            subscription_address,
            "data.google_project.this",
        }

        outputs = pubsub_live_runner.output_json()

        assert "topic_ids" in outputs
        assert "subscription_ids" in outputs
        assert "dead_letter_topic_ids" in outputs

        topic_ids = outputs["topic_ids"].get("value", {})
        subscription_ids = outputs["subscription_ids"].get("value", {})
        dead_letter_topic_ids = outputs["dead_letter_topic_ids"].get(
            "value", {}
        )

        assert live_topic_name in topic_ids
        assert live_subscription_name in subscription_ids
        assert dead_letter_topic_ids == {}

        assert topic_ids[live_topic_name].endswith(
            f"/topics/{live_topic_name}"
        )
        assert subscription_ids[live_subscription_name].endswith(
            f"/subscriptions/{live_subscription_name}"
        )

        state_json = pubsub_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_topic_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == topic_address
        ]

        assert len(matching_topic_resources) == 1
        assert (
            matching_topic_resources[0].get("values", {}).get("name")
            == live_topic_name
        )

        matching_subscription_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == subscription_address
        ]

        assert len(matching_subscription_resources) == 1

        subscription_values = matching_subscription_resources[0].get(
            "values", {}
        )

        assert subscription_values.get("name") == live_subscription_name

        expiration_policy = subscription_values.get(
            "expiration_policy", []
        )

        assert expiration_policy
        assert expiration_policy[0].get("ttl") == ""

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = pubsub_live_runner.state_list()

            if apply_completed or (
                topic_address in state_resources
                or subscription_address in state_resources
            ):
                destroy_result = pubsub_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    pubsub_live_runner.state_list()
                )

                assert topic_address not in remaining_resources
                assert subscription_address not in remaining_resources

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Pub/Sub E2E test failed and cleanup also failed.\n\n"
            f"Test failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Pub/Sub E2E infrastructure verification passed, "
            "but Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

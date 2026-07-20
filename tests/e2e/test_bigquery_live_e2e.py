"""Live end-to-end test for a generated BigQuery Terraform project.

This test creates a real BigQuery dataset and table, verifies them against
live Terraform/GCP state, and always destroys them during cleanup -- even
if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by the existing GCS, Secret Manager, IAM, and Pub/Sub live tests.

Notable difference from the plan-only BigQuery E2E suite: the generator
defaults `deletion_protection = true` on the table resource. Terraform
refuses to destroy a resource with deletion_protection enabled, so this
live test explicitly overrides it to `false` when generating the
workspace. This was verified against current Google provider documentation
before writing this test: `google_bigquery_dataset` itself has no
`deletion_protection`-style field of its own (only an optional
`deletion_policy` this generator doesn't set), so the table-level override
is the only one needed. The table is destroyed before the dataset (an
implicit Terraform dependency via `dataset_id =
google_bigquery_dataset.this.dataset_id`), so the dataset's
`delete_contents_on_destroy = false` setting never becomes an obstacle --
the dataset is already empty of Terraform-managed content by the time its
own destroy runs.
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
from terraform_agent.generators.bigquery.generator import BigQueryGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "bigquery-live-e2e-test"

TABLE_ID = "events"
DATASET_ADDRESS = "google_bigquery_dataset.this"
TABLE_ADDRESS = f'google_bigquery_table.this["{TABLE_ID}"]'

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_dataset_id() -> str:
    """Create a unique, valid BigQuery dataset_id for this test run."""

    timestamp_suffix = format(int(time.time()) % 100000, "x")
    random_suffix = uuid4().hex[:6]

    return f"bigquery_e2e_{timestamp_suffix}{random_suffix}"


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
    """Return the real GCP project ID used for live BigQuery testing."""

    project_id = (
        os.getenv("BIGQUERY_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live BigQuery test. "
            "Set BIGQUERY_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_dataset_id() -> str:
    """Return a unique dataset_id for this test execution."""

    return create_unique_dataset_id()


@pytest.fixture(scope="module")
def bigquery_live_workspace(
    repository_root: Path,
    live_dataset_id: str,
) -> Path:
    """Generate a fresh BigQuery workspace with deletion_protection off."""

    generator = BigQueryGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "dataset_id": live_dataset_id,
                # Deliberately overridden: the generator defaults this to
                # True, which would block `terraform destroy` during
                # cleanup. See module docstring for why the dataset
                # resource itself needs no equivalent override.
                "deletion_protection": False,
                "environment": "dev",
                "owner": "platform-team",
                "application": "bigquery-live-e2e",
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
    bigquery_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = bigquery_live_workspace / "terraform.tfvars.example"
    live_file = bigquery_live_workspace / "terraform.live.tfvars"

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
def bigquery_live_runner(
    bigquery_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live BigQuery workspace."""

    return terraform_runner_factory(bigquery_live_workspace)


def test_bigquery_live_apply_verify_and_destroy(
    bigquery_live_runner: TerraformRunner,
    live_var_file: Path,
    live_dataset_id: str,
) -> None:
    """Deploy, verify, and destroy a real BigQuery dataset and table."""

    plan_file = (
        bigquery_live_runner.working_directory / "bigquery-live-e2e.tfplan"
    )

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        init_result = bigquery_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = bigquery_live_runner.validate()
        assert validate_result.succeeded

        plan_result = bigquery_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = bigquery_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert DATASET_ADDRESS in resource_addresses
        assert TABLE_ADDRESS in resource_addresses

        dataset_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == DATASET_ADDRESS
        ]

        assert len(dataset_changes) == 1
        assert (
            dataset_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        apply_result = bigquery_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(bigquery_live_runner.state_list())

        assert DATASET_ADDRESS in state_resources
        assert TABLE_ADDRESS in state_resources
        assert state_resources == {DATASET_ADDRESS, TABLE_ADDRESS}

        outputs = bigquery_live_runner.output_json()

        assert "dataset_id" in outputs
        assert "dataset_self_link" in outputs
        assert "table_ids" in outputs

        assert outputs["dataset_id"].get("value") == live_dataset_id

        table_ids = outputs["table_ids"].get("value", {})

        assert TABLE_ID in table_ids
        assert live_dataset_id in table_ids[TABLE_ID]

        state_json = bigquery_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_dataset_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == DATASET_ADDRESS
        ]

        assert len(matching_dataset_resources) == 1

        dataset_values = matching_dataset_resources[0].get("values", {})

        assert dataset_values.get("dataset_id") == live_dataset_id
        assert dataset_values.get("delete_contents_on_destroy") is False

        matching_table_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == TABLE_ADDRESS
        ]

        assert len(matching_table_resources) == 1

        table_values = matching_table_resources[0].get("values", {})

        assert table_values.get("table_id") == TABLE_ID
        assert table_values.get("deletion_protection") is False

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(bigquery_live_runner.state_list())

            if apply_completed or (
                DATASET_ADDRESS in state_resources
                or TABLE_ADDRESS in state_resources
            ):
                destroy_result = bigquery_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    bigquery_live_runner.state_list()
                )

                assert DATASET_ADDRESS not in remaining_resources
                assert TABLE_ADDRESS not in remaining_resources

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live BigQuery E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live BigQuery E2E infrastructure verification passed, "
            "but Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

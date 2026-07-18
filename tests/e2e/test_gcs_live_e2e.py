"""Live end-to-end test for a generated GCS Terraform project.

This test creates a real Google Cloud Storage bucket, verifies the Terraform
state and outputs, and destroys the bucket during cleanup.

The test is skipped unless TERRAFORM_E2E_LIVE=true is configured.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "gcs-e2e-test"
RESOURCE_ADDRESS = "google_storage_bucket.this"

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_bucket_name() -> str:
    """Create a globally unique and GCS-compatible bucket name."""

    timestamp = int(time.time())
    random_suffix = uuid4().hex[:8]

    bucket_name = (
        f"terraform-adk-live-e2e-{timestamp}-{random_suffix}"
    ).lower()

    return bucket_name[:63].rstrip("-")


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
def gcs_live_workspace(
    repository_root: Path,
    live_e2e_enabled: None,
) -> Path:
    """Return the generated GCS workspace."""

    workspace = repository_root / "generated" / WORKSPACE_NAME

    if not workspace.exists():
        pytest.fail(
            f"Generated GCS workspace does not exist: {workspace}"
        )

    if not workspace.is_dir():
        pytest.fail(
            f"Generated GCS workspace is not a directory: {workspace}"
        )

    return workspace


@pytest.fixture(scope="module")
def live_bucket_name() -> str:
    """Return a unique GCS bucket name for this test execution."""

    return create_unique_bucket_name()


@pytest.fixture(scope="module")
def live_var_file(
    gcs_live_workspace: Path,
    live_bucket_name: str,
) -> Path:
    """Create a temporary tfvars file containing a unique bucket name."""

    example_file = gcs_live_workspace / "terraform.tfvars.example"
    live_file = gcs_live_workspace / "terraform.live.tfvars"

    if not example_file.exists():
        pytest.fail(
            f"Terraform variable example does not exist: {example_file}"
        )

    example_content = example_file.read_text(encoding="utf-8")

    live_content = replace_tfvars_string_value(
        content=example_content,
        variable_name="bucket_name",
        value=live_bucket_name,
    )

    live_file.write_text(
        live_content,
        encoding="utf-8",
    )

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def gcs_live_runner(
    gcs_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated GCS workspace."""

    return terraform_runner_factory(gcs_live_workspace)


def test_gcs_live_apply_verify_and_destroy(
    gcs_live_runner: TerraformRunner,
    live_var_file: Path,
    live_bucket_name: str,
) -> None:
    """Deploy, verify, and destroy a real GCS bucket."""

    plan_file = gcs_live_runner.working_directory / "gcs-live-e2e.tfplan"

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        init_result = gcs_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = gcs_live_runner.validate()
        assert validate_result.succeeded

        plan_result = gcs_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = gcs_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        matching_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == RESOURCE_ADDRESS
        ]

        assert len(matching_changes) == 1
        assert (
            matching_changes[0]
            .get("change", {})
            .get("actions", [])
            == ["create"]
        )

        apply_result = gcs_live_runner.apply(
            plan_file=plan_result.plan_file,
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = gcs_live_runner.state_list()

        assert RESOURCE_ADDRESS in state_resources
        assert state_resources == [RESOURCE_ADDRESS]

        outputs = gcs_live_runner.output_json()

        assert "bucket_name" in outputs
        assert "bucket_url" in outputs

        bucket_name_output = outputs["bucket_name"]
        bucket_url_output = outputs["bucket_url"]

        assert bucket_name_output.get("value") == live_bucket_name
        assert bucket_name_output.get("sensitive") is False

        expected_bucket_url = f"gs://{live_bucket_name}"

        assert bucket_url_output.get("value") == expected_bucket_url
        assert bucket_url_output.get("sensitive") is False

        state_json = gcs_live_runner.show_json()

        state_resources_json = (
            state_json
            .get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_state_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == RESOURCE_ADDRESS
        ]

        assert len(matching_state_resources) == 1

        bucket_values = matching_state_resources[0].get("values", {})

        assert bucket_values.get("name") == live_bucket_name
        assert (
            bucket_values.get("project")
            == "dhg-vaccine-rateauto-nonpord"
        )
        assert bucket_values.get("location") == "ASIA-SOUTH1"
        assert bucket_values.get("storage_class") == "STANDARD"
        assert bucket_values.get("uniform_bucket_level_access") is True
        assert bucket_values.get("public_access_prevention") == "enforced"

        versioning = bucket_values.get("versioning", [])

        assert versioning
        assert versioning[0].get("enabled") is True

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = gcs_live_runner.state_list()

            if apply_completed or RESOURCE_ADDRESS in state_resources:
                destroy_result = gcs_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!"
                    in destroy_result.combined_output
                )

                remaining_resources = gcs_live_runner.state_list()

                assert RESOURCE_ADDRESS not in remaining_resources
                assert remaining_resources == []

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live GCS E2E test failed and cleanup also failed.\n\n"
            f"Test failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live GCS E2E infrastructure verification passed, "
            "but Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

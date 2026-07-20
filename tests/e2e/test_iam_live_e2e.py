"""Live end-to-end test for a generated IAM Terraform project.

This test creates a real dedicated service account and two real project IAM
role bindings, verifies them against live Terraform/GCP state, and always
destroys them during cleanup -- even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by the existing GCS and Secret Manager live tests.

Unlike the safe (plan-only) IAM E2E suite, this test:

- Requires a real GCP project ID (via IAM_E2E_PROJECT_ID, falling back to
  GOOGLE_CLOUD_PROJECT) since it creates real resources.
- Generates a workspace directly from IAMGenerator with a unique
  service_account_id per run (timestamp + random suffix). This matters more
  here than for most generators: a deleted service account's ID/email can
  become temporarily unusable for a new service account for a period after
  deletion, so reusing a fixed ID across repeated live-test runs risks a
  spurious failure that has nothing to do with the generator itself.
- Grants two intentionally harmless, no-op project roles
  (roles/cloudsql.client, roles/secretmanager.secretAccessor) so the IAM
  bindings created have no real effect beyond existing as bindings to
  verify and tear down.
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
from terraform_agent.generators.iam.generator import IAMGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "iam-live-e2e-test"

SERVICE_ACCOUNT_ADDRESS = "google_service_account.this"
ROLE_ADDRESSES = {
    'google_project_iam_member.runtime_roles["roles/cloudsql.client"]',
    'google_project_iam_member.runtime_roles["roles/secretmanager.secretAccessor"]',
}
PROJECT_ROLES = [
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
]

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_service_account_id() -> str:
    """Create a unique, valid service_account_id for this test run."""

    timestamp_suffix = format(int(time.time()) % 100000, "x")
    random_suffix = uuid4().hex[:6]

    account_id = f"iam-e2e-{timestamp_suffix}{random_suffix}"

    return account_id[:30]


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
    """Return the real GCP project ID used for live IAM testing."""

    project_id = (
        os.getenv("IAM_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live IAM test. "
            "Set IAM_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a real "
            "GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_service_account_id() -> str:
    """Return a unique service_account_id for this test execution."""

    return create_unique_service_account_id()


@pytest.fixture(scope="module")
def iam_live_workspace(
    repository_root: Path,
    live_service_account_id: str,
) -> Path:
    """Generate a fresh IAM workspace with a unique service account ID."""

    generator = IAMGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "service_account_id": live_service_account_id,
                "project_roles": PROJECT_ROLES,
                "environment": "dev",
                "owner": "platform-team",
                "application": "iam-live-e2e",
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
    iam_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = iam_live_workspace / "terraform.tfvars.example"
    live_file = iam_live_workspace / "terraform.live.tfvars"

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
def iam_live_runner(
    iam_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live IAM workspace."""

    return terraform_runner_factory(iam_live_workspace)


def test_iam_live_apply_verify_and_destroy(
    iam_live_runner: TerraformRunner,
    live_var_file: Path,
    live_service_account_id: str,
    live_project_id: str,
) -> None:
    """Deploy, verify, and destroy a real service account and IAM bindings."""

    plan_file = iam_live_runner.working_directory / "iam-live-e2e.tfplan"

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        init_result = iam_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = iam_live_runner.validate()
        assert validate_result.succeeded

        plan_result = iam_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = iam_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert SERVICE_ACCOUNT_ADDRESS in resource_addresses
        assert ROLE_ADDRESSES.issubset(resource_addresses)

        service_account_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == SERVICE_ACCOUNT_ADDRESS
        ]

        assert len(service_account_changes) == 1
        assert (
            service_account_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        apply_result = iam_live_runner.apply(plan_file=plan_result.plan_file)

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = iam_live_runner.state_list()

        assert SERVICE_ACCOUNT_ADDRESS in state_resources
        assert ROLE_ADDRESSES.issubset(set(state_resources))
        assert set(state_resources) == {
            SERVICE_ACCOUNT_ADDRESS,
            *ROLE_ADDRESSES,
        }

        outputs = iam_live_runner.output_json()

        assert "service_account_id" in outputs
        assert "service_account_email" in outputs
        assert "service_account_member" in outputs
        assert "granted_project_roles" in outputs

        assert (
            outputs["service_account_id"].get("value")
            == live_service_account_id
        )

        expected_email_suffix = (
            f"@{live_project_id}.iam.gserviceaccount.com"
        )

        service_account_email = outputs["service_account_email"].get(
            "value"
        )

        assert service_account_email.startswith(live_service_account_id)
        assert service_account_email.endswith(expected_email_suffix)

        expected_member = f"serviceAccount:{service_account_email}"

        assert (
            outputs["service_account_member"].get("value")
            == expected_member
        )

        granted_roles = outputs["granted_project_roles"].get("value")

        assert set(granted_roles) == set(PROJECT_ROLES)

        state_json = iam_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_state_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == SERVICE_ACCOUNT_ADDRESS
        ]

        assert len(matching_state_resources) == 1

        service_account_values = matching_state_resources[0].get(
            "values", {}
        )

        assert (
            service_account_values.get("account_id")
            == live_service_account_id
        )
        assert service_account_values.get("project") == live_project_id

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = iam_live_runner.state_list()

            if apply_completed or state_resources:
                destroy_result = iam_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = iam_live_runner.state_list()

                assert not remaining_resources

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live IAM E2E test failed and cleanup also failed.\n\n"
            f"Test failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live IAM E2E infrastructure verification passed, but "
            "Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

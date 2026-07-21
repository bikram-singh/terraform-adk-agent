"""Live end-to-end test for a generated Cloud Run Terraform project.

This test creates a real dedicated runtime service account and a real
Cloud Run v2 service, verifies them against live Terraform/GCP state, and
always destroys them during cleanup -- even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This one should be one of the fastest live tests in this phase.** Unlike
Cloud Functions, it does not trigger a build: it points directly at
Google's public `gcr.io/cloudrun/hello` sample image, so there is no
Cloud Build step, no source bucket, and no custom container to package.
With the generator's defaults, only two resources are created (the
runtime service account and the Cloud Run service itself) -- no VPC
connector, no Cloud SQL volume, no extra IAM bindings, no public invoker.
Expect well under two minutes.

The generator defaults `deletion_protection = true` on the Cloud Run
service, which would block `terraform destroy` during cleanup, so this
test explicitly overrides it to `false` when generating the workspace
(the same pattern used for the BigQuery live test).

`ingress` defaults to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` and
`allow_unauthenticated` defaults to `false` (the generator's secure
defaults), so this test does not attempt to invoke the deployed service
over HTTP -- it verifies existence and configuration via Terraform state
and outputs only, consistent with the verification depth of every other
live test in this suite.
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
from terraform_agent.generators.cloudrun.generator import CloudRunGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloudrun-live-e2e-test"

SERVICE_ACCOUNT_ADDRESS = "google_service_account.runtime"
SERVICE_ADDRESS = "google_cloud_run_v2_service.this"

EXPECTED_RESOURCE_ADDRESSES = {
    SERVICE_ACCOUNT_ADDRESS,
    SERVICE_ADDRESS,
}

CONTAINER_IMAGE = "gcr.io/cloudrun/hello"

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_service_name() -> str:
    """Create a unique, valid Cloud Run service_name for this test run."""

    suffix = uuid4().hex[:6]

    return f"run-e2e-{suffix}"


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
    """Return the real GCP project ID used for live Cloud Run testing."""

    project_id = (
        os.getenv("CLOUD_RUN_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Cloud Run test. "
            "Set CLOUD_RUN_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_service_name() -> str:
    """Return a unique service_name for this test execution."""

    return create_unique_service_name()


@pytest.fixture(scope="module")
def cloudrun_live_workspace(
    repository_root: Path,
    live_service_name: str,
) -> Path:
    """Generate a fresh Cloud Run workspace with deletion_protection off."""

    generator = CloudRunGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "service_name": live_service_name,
                "container_image": CONTAINER_IMAGE,
                # Deliberately overridden: the generator defaults this to
                # True, which would block `terraform destroy` during
                # cleanup.
                "deletion_protection": False,
                "environment": "dev",
                "owner": "platform-team",
                "application": "cloudrun-live-e2e",
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
    cloudrun_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = cloudrun_live_workspace / "terraform.tfvars.example"
    live_file = cloudrun_live_workspace / "terraform.live.tfvars"

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
def cloudrun_live_runner(
    cloudrun_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live Cloud Run workspace."""

    return terraform_runner_factory(cloudrun_live_workspace)


def test_cloud_run_live_apply_verify_and_destroy(
    cloudrun_live_runner: TerraformRunner,
    live_var_file: Path,
    live_service_name: str,
) -> None:
    """Deploy, verify, and destroy a real Cloud Run service end to end."""

    plan_file = (
        cloudrun_live_runner.working_directory / "cloudrun-live-e2e.tfplan"
    )

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = cloudrun_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = cloudrun_live_runner.validate()
        assert validate_result.succeeded

        plan_result = cloudrun_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = cloudrun_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

        service_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == SERVICE_ADDRESS
        ]

        assert len(service_changes) == 1
        assert (
            service_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        apply_result = cloudrun_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(cloudrun_live_runner.state_list())

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(state_resources)
        assert state_resources == EXPECTED_RESOURCE_ADDRESSES

        outputs = cloudrun_live_runner.output_json()

        assert "service_name" in outputs
        assert "service_uri" in outputs
        assert "runtime_service_account_email" in outputs
        assert "service_location" in outputs

        assert outputs["service_name"].get("value") == live_service_name
        assert outputs["service_location"].get("value") == "asia-south1"

        service_uri = outputs["service_uri"].get("value")

        assert service_uri
        assert service_uri.startswith("https://")

        state_json = cloudrun_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_service_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == SERVICE_ADDRESS
        ]

        assert len(matching_service_resources) == 1

        service_values = matching_service_resources[0].get("values", {})

        assert service_values.get("name") == live_service_name
        assert (
            service_values.get("ingress")
            == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
        )
        assert service_values.get("deletion_protection") is False

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(cloudrun_live_runner.state_list())

            if apply_completed or (
                EXPECTED_RESOURCE_ADDRESSES & state_resources
            ):
                destroy_result = cloudrun_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    cloudrun_live_runner.state_list()
                )

                assert not (
                    EXPECTED_RESOURCE_ADDRESSES & remaining_resources
                )

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"\nLive Cloud Run E2E test took {elapsed_seconds:.1f}s "
        "(apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Run E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Run E2E infrastructure verification passed, "
            "but Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

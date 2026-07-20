"""Live end-to-end test for a generated Cloud Functions Terraform project.

This test creates a real, dedicated source bucket, uploads a real deployable
zip, deploys a real Cloud Functions (2nd gen) HTTP function, verifies it
against live Terraform/GCP state, and always destroys everything during
cleanup -- even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This one is different from every previous live test in one important
way: it triggers a real Cloud Build.** Cloud Functions 2nd gen deploys via
Cloud Build + Cloud Run under the hood, not a direct API call, so:

- Expect roughly 3-8 minutes end to end (build + deploy + verify +
  destroy), similar in scale to the Network live test, though usually
  somewhat faster.
- A minimal `requirements.txt` pinning `functions-framework` is included
  alongside `main.py` in the deployable zip. Cloud Build's buildpacks can
  sometimes auto-detect Python functions without it, but pinning it
  explicitly removes that ambiguity and gives the build the best chance of
  succeeding on the first try.
- If this fails, check whether it failed during the Terraform apply itself
  (a Terraform/GCP API problem, same class of issue as previous live
  tests) or during the underlying Cloud Build (a packaging/build problem,
  a new failure mode not seen in earlier live tests). The Cloud Build logs
  are visible in the GCP Console under Cloud Build > History if needed.
- Real cost here is still small (a few seconds of Cloud Build time, a tiny
  amount of Artifact Registry storage for the built container image, and
  trivial GCS storage for the source zip) but is not literally zero the
  way IAM or Pub/Sub were.

`ingress_settings` defaults to `ALLOW_INTERNAL_ONLY` (the generator's
secure default), so this test does not attempt to invoke the deployed
function over HTTP -- it verifies the function exists with the expected
configuration via Terraform state and outputs, then tears it down, the
same verification depth as every other live test in this suite.
"""

from __future__ import annotations

import os
import re
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.cloud_functions.generator import (
    CloudFunctionsGenerator,
)

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloud-functions-live-e2e-test"

BUCKET_ADDRESS = "google_storage_bucket.source"
OBJECT_ADDRESS = "google_storage_bucket_object.source_archive"
SERVICE_ACCOUNT_ADDRESS = "google_service_account.runtime"
FUNCTION_ADDRESS = "google_cloudfunctions2_function.this"
TIME_SLEEP_ADDRESS = "time_sleep.wait_for_runtime_sa_propagation"

EXPECTED_RESOURCE_ADDRESSES = {
    BUCKET_ADDRESS,
    OBJECT_ADDRESS,
    SERVICE_ACCOUNT_ADDRESS,
    FUNCTION_ADDRESS,
    TIME_SLEEP_ADDRESS,
}

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid resource names for this test run.

    The source bucket needs its own, more-random suffix than the function
    name: GCS bucket names are globally unique across all of GCP, not just
    within the project, so it gets more entropy to keep collision risk
    negligible even across many repeated live-test runs over time.
    """

    function_suffix = uuid4().hex[:6]
    bucket_suffix = uuid4().hex[:12]

    return {
        "function_name": f"fn-e2e-{function_suffix}",
        "source_bucket_name": f"fn-e2e-{bucket_suffix}",
    }


def create_deployable_source_archive(destination: Path) -> None:
    """Create a minimal, real deployable zip for a Python HTTP function.

    Includes requirements.txt pinning functions-framework so Cloud Build's
    buildpacks have no ambiguity to resolve during the real build.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "main.py",
            "import functions_framework\n\n"
            "@functions_framework.http\n"
            "def main(request):\n"
            "    return 'ok'\n",
        )
        archive.writestr(
            "requirements.txt",
            "functions-framework==3.*\n",
        )


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
    """Return the real GCP project ID used for live Cloud Functions testing."""

    project_id = (
        os.getenv("CLOUD_FUNCTIONS_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Cloud Functions test. "
            "Set CLOUD_FUNCTIONS_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) "
            "to a real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def cloud_functions_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Generate a fresh Cloud Functions workspace with unique names."""

    generator = CloudFunctionsGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "function_name": live_names["function_name"],
                "source_bucket_name": live_names["source_bucket_name"],
                "environment": "dev",
                "owner": "platform-team",
                "application": "cloud-functions-live-e2e",
            },
        )
    )

    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    for name, content in project.files.items():
        (workspace / name).write_text(content, encoding="utf-8")

    return workspace


@pytest.fixture(scope="module")
def live_source_archive(cloud_functions_live_workspace: Path) -> Path:
    """Create the real deployable zip referenced by terraform.tfvars."""

    archive_path = (
        cloud_functions_live_workspace / "dist" / "function-source.zip"
    )

    create_deployable_source_archive(archive_path)

    return archive_path


@pytest.fixture(scope="module")
def live_var_file(
    cloud_functions_live_workspace: Path,
    live_project_id: str,
    live_source_archive: Path,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = (
        cloud_functions_live_workspace / "terraform.tfvars.example"
    )
    live_file = cloud_functions_live_workspace / "terraform.live.tfvars"

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
def cloud_functions_live_runner(
    cloud_functions_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the live Cloud Functions workspace."""

    return terraform_runner_factory(cloud_functions_live_workspace)


def test_cloud_functions_live_apply_verify_and_destroy(
    cloud_functions_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
) -> None:
    """Deploy, verify, and destroy a real Cloud Function end to end."""

    plan_file = (
        cloud_functions_live_runner.working_directory
        / "cloud-functions-live-e2e.tfplan"
    )

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = cloud_functions_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = cloud_functions_live_runner.validate()
        assert validate_result.succeeded

        plan_result = cloud_functions_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = cloud_functions_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

        function_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == FUNCTION_ADDRESS
        ]

        assert len(function_changes) == 1
        assert (
            function_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        # This is the slow part: a real Cloud Build runs here, packaging
        # and deploying the function to Cloud Run under the hood.
        apply_result = cloud_functions_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(cloud_functions_live_runner.state_list())

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(state_resources)
        assert state_resources == EXPECTED_RESOURCE_ADDRESSES

        outputs = cloud_functions_live_runner.output_json()

        assert "function_name" in outputs
        assert "function_uri" in outputs
        assert "runtime_service_account_email" in outputs
        assert "source_bucket_name" in outputs

        assert (
            outputs["function_name"].get("value")
            == live_names["function_name"]
        )
        assert (
            outputs["source_bucket_name"].get("value")
            == live_names["source_bucket_name"]
        )

        function_uri = outputs["function_uri"].get("value")

        assert function_uri
        assert function_uri.startswith("https://")

        state_json = cloud_functions_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_function_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == FUNCTION_ADDRESS
        ]

        assert len(matching_function_resources) == 1

        function_values = matching_function_resources[0].get("values", {})

        assert function_values.get("name") == live_names["function_name"]

        service_config = function_values.get("service_config", [])

        assert service_config
        assert (
            service_config[0].get("ingress_settings")
            == "ALLOW_INTERNAL_ONLY"
        )

        matching_bucket_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == BUCKET_ADDRESS
        ]

        assert len(matching_bucket_resources) == 1
        assert (
            matching_bucket_resources[0].get("values", {}).get("name")
            == live_names["source_bucket_name"]
        )

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(
                cloud_functions_live_runner.state_list()
            )

            if apply_completed or (
                EXPECTED_RESOURCE_ADDRESSES & state_resources
            ):
                destroy_result = cloud_functions_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    cloud_functions_live_runner.state_list()
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
        f"\nLive Cloud Functions E2E test took {elapsed_seconds:.1f}s "
        "(build + apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Functions E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Functions E2E infrastructure verification "
            "passed, but Terraform cleanup failed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

"""Live end-to-end test for a generated Network (VPC) Terraform project.

This test creates a real custom-mode VPC network, a regional subnet, a
Private Service Access peering connection, and a Serverless VPC Access
connector -- verifies them against live Terraform/GCP state, and always
destroys them during cleanup, even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This one is meaningfully slower than the other live tests.** The
Serverless VPC Access connector alone typically takes several minutes to
provision and several minutes to tear down, and the Private Service Access
peering connection is not instantaneous either. Expect this test to take
somewhere in the 5-15 minute range end to end, not the ~40-80 seconds seen
for IAM, Pub/Sub, and BigQuery. Do not interrupt a run in progress: an
interrupted apply or destroy is exactly the scenario most likely to leave
a partially-provisioned VPC connector or PSA peering behind, which then
has to be cleaned up by hand.

`google_service_networking_connection` (the PSA peering resource) also has
a known real-world quirk: it can occasionally be slow to tear down, or in
rare cases needs a retry, if GCP's async service-producer bookkeeping
hasn't fully caught up yet. This isn't a defect in the generator or this
test -- it's a documented characteristic of that resource across the
Google provider ecosystem. If a destroy fails here, re-running
`terraform destroy` in the workspace directly (or waiting a minute and
retrying the pytest invocation) is a reasonable next step before assuming
something is actually wrong.
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
from terraform_agent.generators.network.generator import NetworkGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "network-live-e2e-test"

NETWORK_ADDRESS = "google_compute_network.this"
SUBNET_ADDRESS = "google_compute_subnetwork.this"
PSA_RANGE_ADDRESS = "google_compute_global_address.private_service_range"
PSA_CONNECTION_ADDRESS = (
    "google_service_networking_connection.private_service_access"
)
VPC_CONNECTOR_ADDRESS = "google_vpc_access_connector.serverless[0]"

EXPECTED_RESOURCE_ADDRESSES = {
    NETWORK_ADDRESS,
    SUBNET_ADDRESS,
    PSA_RANGE_ADDRESS,
    PSA_CONNECTION_ADDRESS,
    VPC_CONNECTOR_ADDRESS,
}

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid resource names for this test run.

    A shared random suffix ties the names together for easy identification
    in the GCP console, while the vpc_connector_name is built from a short
    dedicated prefix to stay within its 25-character limit regardless of
    how long the network name ends up being.
    """

    suffix = uuid4().hex[:6]

    network_name = f"net-e2e-{suffix}"

    return {
        "network_name": network_name,
        "subnet_name": f"{network_name}-subnet",
        "private_service_access_range_name": f"{network_name}-psa",
        "vpc_connector_name": f"vpc-e2e-{suffix}",
    }


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
    """Return the real GCP project ID used for live Network testing."""

    project_id = (
        os.getenv("NETWORK_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Network test. "
            "Set NETWORK_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def network_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Generate a fresh Network workspace with unique resource names."""

    generator = NetworkGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "network_name": live_names["network_name"],
                "subnet_name": live_names["subnet_name"],
                "private_service_access_range_name": live_names[
                    "private_service_access_range_name"
                ],
                "vpc_connector_name": live_names["vpc_connector_name"],
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
    network_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = network_live_workspace / "terraform.tfvars.example"
    live_file = network_live_workspace / "terraform.live.tfvars"

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
def network_live_runner(
    network_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live Network workspace."""

    return terraform_runner_factory(network_live_workspace)


def test_network_live_apply_verify_and_destroy(
    network_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
) -> None:
    """Deploy, verify, and destroy a real VPC networking foundation."""

    plan_file = (
        network_live_runner.working_directory / "network-live-e2e.tfplan"
    )

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = network_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = network_live_runner.validate()
        assert validate_result.succeeded

        plan_result = network_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = network_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

        network_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == NETWORK_ADDRESS
        ]

        assert len(network_changes) == 1
        assert (
            network_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        # This is the slow part: VPC connector provisioning typically
        # takes several minutes, plus PSA peering setup on top of that.
        apply_result = network_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(network_live_runner.state_list())

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(state_resources)
        assert state_resources == EXPECTED_RESOURCE_ADDRESSES

        outputs = network_live_runner.output_json()

        assert "network_id" in outputs
        assert "network_name" in outputs
        assert "subnet_id" in outputs
        assert "subnet_name" in outputs
        assert "private_service_access_connection" in outputs
        assert "vpc_connector_id" in outputs
        assert "vpc_connector_name" in outputs

        assert (
            outputs["network_name"].get("value")
            == live_names["network_name"]
        )
        assert (
            outputs["subnet_name"].get("value")
            == live_names["subnet_name"]
        )
        assert (
            outputs["vpc_connector_name"].get("value")
            == live_names["vpc_connector_name"]
        )
        assert outputs["vpc_connector_id"].get("value") is not None

        state_json = network_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_network_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == NETWORK_ADDRESS
        ]

        assert len(matching_network_resources) == 1
        assert (
            matching_network_resources[0].get("values", {}).get("name")
            == live_names["network_name"]
        )

        matching_connector_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == VPC_CONNECTOR_ADDRESS
        ]

        assert len(matching_connector_resources) == 1
        assert (
            matching_connector_resources[0].get("values", {}).get("name")
            == live_names["vpc_connector_name"]
        )

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(network_live_runner.state_list())

            if apply_completed or (
                EXPECTED_RESOURCE_ADDRESSES & state_resources
            ):
                # Also the slow part in reverse: connector and PSA
                # teardown take real time. Terraform handles the
                # dependency ordering (connector/PSA before network)
                # automatically.
                destroy_result = network_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    network_live_runner.state_list()
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
        f"\nLive Network E2E test took {elapsed_seconds:.1f}s "
        "(apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Network E2E test failed and cleanup also failed.\n\n"
            f"Test failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Network E2E infrastructure verification passed, "
            "but Terraform cleanup failed. If this was a transient "
            "google_service_networking_connection or VPC connector "
            "teardown delay, re-running `terraform destroy` directly in "
            f"the workspace ({network_live_runner.working_directory}) "
            "is a reasonable next step.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

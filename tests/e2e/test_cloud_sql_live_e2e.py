"""Live end-to-end test for a generated Cloud SQL Terraform project.

This test creates a real, private-IP-only Cloud SQL instance and one
application database, verifies them against live Terraform/GCP state, and
always destroys them during cleanup -- even if an earlier assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This one is the slowest and most expensive live test so far, and it has
a hard external prerequisite the other generators don't.** Cloud SQL's
`private_network` variable has no default: it must reference an existing
VPC that already has Private Service Access configured, since this
generator creates private-IP-only instances by design. Rather than
provisioning a temporary VPC + PSA connection just for this test (which
would add another 5-15 minutes on top of Cloud SQL's own slow create/
destroy), this test points at a VPC that already exists in the target
project.

Set CLOUD_SQL_E2E_PRIVATE_NETWORK to the full self-link of that VPC
before running, for example:

    projects/dhg-vaccine-rateauto-nonpord/global/networks/default

If you're not sure of the exact self-link, list your networks first:

    gcloud compute networks list --project=<project>

and confirm it has Private Service Access configured:

    gcloud services vpc-peerings list --network=<network-name> --project=<project>

**Expect this test to take a while -- realistically 10-20 minutes.** Cloud
SQL instance creation and deletion are both slow regardless of machine
tier; this test deliberately uses the smallest reasonable footprint
(`db-custom-1-3840`, `ZONAL` availability, a 10 GB disk) to keep it as
fast as a Cloud SQL test can be, but it will still be much slower than
IAM/Pub-Sub/BigQuery/Cloud Run. Do not interrupt a run in progress, for
the same reason as the Network live test: an interrupted apply or destroy
here is the scenario most likely to leave a real, billable instance
behind.

Cloud SQL instance names also cannot be reused for a period after
deletion (Cloud SQL reserves recently-deleted instance names), so this
test uses a strongly unique name per run (timestamp + random suffix), not
just a short random suffix.
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
from terraform_agent.generators.cloudsql.generator import CloudSQLGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloudsql-live-e2e-test"

INSTANCE_ADDRESS = "google_sql_database_instance.this"
DATABASE_ADDRESS = "google_sql_database.application"

EXPECTED_RESOURCE_ADDRESSES = {
    INSTANCE_ADDRESS,
    DATABASE_ADDRESS,
}

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_instance_name() -> str:
    """Create a strongly unique Cloud SQL instance_name for this test run.

    Cloud SQL reserves recently-deleted instance names for a period after
    deletion, so this uses more entropy than a typical short suffix.
    """

    timestamp_suffix = format(int(time.time()) % 1_000_000, "x")
    random_suffix = uuid4().hex[:8]

    return f"sql-e2e-{timestamp_suffix}{random_suffix}"


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
    """Return the real GCP project ID used for live Cloud SQL testing."""

    project_id = (
        os.getenv("CLOUD_SQL_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Cloud SQL test. "
            "Set CLOUD_SQL_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_private_network(live_e2e_enabled: None) -> str:
    """Return the existing VPC self-link with Private Service Access."""

    private_network = os.getenv(
        "CLOUD_SQL_E2E_PRIVATE_NETWORK", ""
    ).strip()

    if not private_network:
        pytest.fail(
            "No existing VPC configured for the live Cloud SQL test. "
            "Set CLOUD_SQL_E2E_PRIVATE_NETWORK to the full self-link of "
            "an existing VPC with Private Service Access, for example: "
            "projects/<project>/global/networks/<network-name>. "
            "This generator requires private-IP-only instances and does "
            "not provision networking prerequisites itself."
        )

    return private_network


@pytest.fixture(scope="module")
def live_instance_name() -> str:
    """Return a unique instance_name for this test execution."""

    return create_unique_instance_name()


@pytest.fixture(scope="module")
def cloudsql_live_workspace(
    repository_root: Path,
    live_instance_name: str,
) -> Path:
    """Generate a fresh Cloud SQL workspace sized down for a live test."""

    generator = CloudSQLGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "instance_name": live_instance_name,
                # Smallest reasonable footprint to keep this as fast as a
                # Cloud SQL live test can realistically be. Edition is
                # pinned explicitly to ENTERPRISE (classic) since
                # db-custom-* tiers are only valid on that edition --
                # some projects/accounts default new instances to
                # ENTERPRISE_PLUS, which requires db-perf-optimized-*
                # tiers instead.
                "tier": "db-custom-1-3840",
                "edition": "ENTERPRISE",
                "availability_type": "ZONAL",
                "disk_size_gb": 10,
                # Deliberately overridden: the generator defaults this to
                # True, which would block `terraform destroy` during
                # cleanup.
                "deletion_protection": False,
                "environment": "dev",
                "owner": "platform-team",
                "application": "cloudsql-live-e2e",
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
    cloudsql_live_workspace: Path,
    live_project_id: str,
    live_private_network: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID and VPC."""

    example_file = cloudsql_live_workspace / "terraform.tfvars.example"
    live_file = cloudsql_live_workspace / "terraform.live.tfvars"

    if not example_file.exists():
        pytest.fail(
            f"Terraform variable example does not exist: {example_file}"
        )

    content = example_file.read_text(encoding="utf-8")

    content = replace_tfvars_string_value(
        content=content,
        variable_name="project_id",
        value=live_project_id,
    )
    content = replace_tfvars_string_value(
        content=content,
        variable_name="private_network",
        value=live_private_network,
    )

    live_file.write_text(content, encoding="utf-8")

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def cloudsql_live_runner(
    cloudsql_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live Cloud SQL workspace."""

    return terraform_runner_factory(cloudsql_live_workspace)


def test_cloud_sql_live_apply_verify_and_destroy(
    cloudsql_live_runner: TerraformRunner,
    live_var_file: Path,
    live_instance_name: str,
) -> None:
    """Deploy, verify, and destroy a real Cloud SQL instance end to end."""

    plan_file = (
        cloudsql_live_runner.working_directory / "cloudsql-live-e2e.tfplan"
    )

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = cloudsql_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = cloudsql_live_runner.validate()
        assert validate_result.succeeded

        plan_result = cloudsql_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = cloudsql_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

        instance_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == INSTANCE_ADDRESS
        ]

        assert len(instance_changes) == 1
        assert (
            instance_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        # This is the slow part: Cloud SQL instance creation typically
        # takes several minutes regardless of machine tier.
        apply_result = cloudsql_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(cloudsql_live_runner.state_list())

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(state_resources)
        assert state_resources == EXPECTED_RESOURCE_ADDRESSES

        outputs = cloudsql_live_runner.output_json()

        assert "instance_name" in outputs
        assert "connection_name" in outputs
        assert "private_ip_address" in outputs
        assert "database_name" in outputs

        assert outputs["instance_name"].get("value") == live_instance_name
        assert outputs["database_name"].get("value") == "application"

        connection_name = outputs["connection_name"].get("value")

        assert connection_name
        assert connection_name.endswith(f":{live_instance_name}")

        private_ip_output = outputs["private_ip_address"]

        assert private_ip_output.get("sensitive") is True
        assert private_ip_output.get("value")

        state_json = cloudsql_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_instance_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == INSTANCE_ADDRESS
        ]

        assert len(matching_instance_resources) == 1

        instance_values = matching_instance_resources[0].get("values", {})

        assert instance_values.get("name") == live_instance_name
        assert instance_values.get("deletion_protection") is False
        assert instance_values.get("database_version") == "POSTGRES_16"

        settings = instance_values.get("settings", [])

        assert settings
        assert settings[0].get("tier") == "db-custom-1-3840"
        assert settings[0].get("edition") == "ENTERPRISE"
        assert settings[0].get("availability_type") == "ZONAL"

        ip_configuration = settings[0].get("ip_configuration", [])

        assert ip_configuration
        assert ip_configuration[0].get("ipv4_enabled") is False

        matching_database_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == DATABASE_ADDRESS
        ]

        assert len(matching_database_resources) == 1
        assert (
            matching_database_resources[0]
            .get("values", {})
            .get("name")
            == "application"
        )

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(cloudsql_live_runner.state_list())

            if apply_completed or (
                EXPECTED_RESOURCE_ADDRESSES & state_resources
            ):
                # Also the slow part in reverse: Cloud SQL deletion
                # typically takes several minutes as well.
                destroy_result = cloudsql_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    cloudsql_live_runner.state_list()
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
        f"\nLive Cloud SQL E2E test took {elapsed_seconds:.1f}s "
        "(apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Cloud SQL E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Cloud SQL E2E infrastructure verification passed, "
            "but Terraform cleanup failed. Since this creates a real "
            "billable Cloud SQL instance, check the GCP Console (or "
            "`gcloud sql instances list`) to confirm nothing was left "
            "behind, and re-run `terraform destroy` directly in the "
            f"workspace ({cloudsql_live_runner.working_directory}) if "
            "needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

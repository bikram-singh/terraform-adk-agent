"""Live end-to-end test for the assembled private Cloud Run + Cloud SQL
platform.

This test assembles the composed architecture (via
`assemble_private_cloud_run_cloud_sql_project`, which writes the full
multi-module workspace directly to `generated/<workspace_name>/`),
deploys it for real, verifies the cross-module wiring, and always
destroys everything during cleanup -- even if an earlier assertion
fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This is likely the single slowest live test in the whole suite**,
slower even than GKE's real-world timing in some runs. Unlike every
other composed/standalone test, this is ONE single `terraform apply`
that must create the network's PSA connection and Serverless VPC Access
connector (which alone took ~9 minutes in the standalone Network live
test) *before* Cloud SQL can even start creating (~10 minutes in the
standalone Cloud SQL live test, though that test pointed at an
already-existing VPC with PSA -- here, Cloud SQL has to wait for PSA to
be provisioned from scratch first, inside the same apply). Realistic
expectation: 20-30+ minutes for apply, roughly matching for destroy.
Given that, this test uses a substantially longer Terraform timeout than
the shared default, the same lesson learned building the GKE live test.

Unlike GKE, this architecture does NOT need custom firewall rules on the
network module's custom-mode VPC: Cloud Run's connection to Cloud SQL
over the Serverless VPC Access connector is egress-initiated (Cloud Run
calls out to Cloud SQL), and GCP's implied firewall rules allow all
egress by default even on custom-mode VPCs -- only ingress is
deny-by-default, which is what actually required explicit firewall rules
for GKE's control-plane-to-node traffic.

This test verifies real infrastructure and cross-module wiring via
Terraform state/outputs, not a full functional application-level check
like the event pipeline's live test: this recipe deliberately generates
no `google_sql_user` and no real database password (per its own README,
the credential must be populated out-of-band), so there's no wired
database connection to actually exercise without deploying custom
application code, which is out of scope here.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from terraform_agent.intelligence.assembler import (
    assemble_private_cloud_run_cloud_sql_project,
)

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "cloudrun-cloudsql-live-e2e-test"

NETWORK_ADDRESS = "module.network.google_compute_network.this"
SUBNET_ADDRESS = "module.network.google_compute_subnetwork.this"
PSA_RANGE_ADDRESS = (
    "module.network.google_compute_global_address.private_service_range"
)
PSA_CONNECTION_ADDRESS = (
    "module.network.google_service_networking_connection."
    "private_service_access"
)
VPC_CONNECTOR_ADDRESS = (
    "module.network.google_vpc_access_connector.serverless[0]"
)
CLOUD_SQL_INSTANCE_ADDRESS = "module.cloud_sql.google_sql_database_instance.this"
CLOUD_SQL_DATABASE_ADDRESS = "module.cloud_sql.google_sql_database.application"
SERVICE_ACCOUNT_ADDRESS = "module.cloud_run.google_service_account.runtime"
CLOUD_RUN_SERVICE_ADDRESS = (
    "module.cloud_run.google_cloud_run_v2_service.this"
)
CLOUD_SQL_CLIENT_ADDRESS = (
    "module.cloud_run.google_project_iam_member.cloud_sql_client[0]"
)
SECRET_ACCESS_ADDRESS = (
    'module.cloud_run.google_secret_manager_secret_iam_member.'
    'secret_access["DB_PASSWORD"]'
)

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid resource names for this test run."""

    suffix = uuid4().hex[:6]

    network_name = f"crcs-e2e-{suffix}"
    service_name = f"crcs-e2e-{suffix}"

    return {
        "network_name": network_name,
        "service_name": service_name,
        "database_secret_id": f"crcs-e2e-{suffix}-db-password",
        "secret_address_key": f"crcs-e2e-{suffix}-db-password",
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
    """Return the real GCP project ID used for this live test."""

    project_id = (
        os.getenv("CRCS_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Cloud Run + Cloud "
            "SQL test. Set CRCS_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) "
            "to a real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def crcs_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Assemble the architecture directly -- the assembler already
    writes the full workspace to generated/<workspace_name>/ on disk."""

    result = assemble_private_cloud_run_cloud_sql_project(
        workspace_name=WORKSPACE_NAME,
        region="asia-south1",
        environment="dev",
        owner="platform-team",
        application=live_names["service_name"],
        network_name=live_names["network_name"],
        database_secret_id=live_names["database_secret_id"],
        service_name=live_names["service_name"],
        # Google's public sample image, matching the standalone Cloud Run
        # live test -- no build step, no custom container needed.
        container_image="gcr.io/cloudrun/hello",
        # Deliberately overridden: the assembler defaults both of these
        # to True (the safe production default), which would block
        # `terraform destroy` during cleanup of this throwaway test
        # workspace.
        db_deletion_protection=False,
        cloud_run_deletion_protection=False,
    )

    if result.get("stage") != "complete":
        pytest.fail(
            f"Architecture assembly failed before file generation: "
            f"{result}"
        )

    workspace = repository_root / "generated" / WORKSPACE_NAME

    # This architecture deliberately generates no secret VERSION, only
    # the secret container (see its own README: the real credential is
    # meant to be populated out-of-band via `gcloud secrets versions
    # add`). Cloud Run's reference to version "latest" fails at creation
    # time without at least one version existing, so this test -- and
    # only this test, not the shared architecture -- adds a placeholder
    # version purely so the deployment can complete.
    placeholder_secret_tf = f"""
resource "google_secret_manager_secret_version" "test_placeholder" {{
  secret      = module.secret_manager.secret_names["{live_names['database_secret_id']}"]
  secret_data = "test-placeholder-not-a-real-credential"
}}
"""
    (workspace / "test_secret_placeholder.tf").write_text(
        placeholder_secret_tf, encoding="utf-8"
    )

    # The PSA (`google_service_networking_connection`) teardown in this
    # specific project has consistently (confirmed across 5+ separate
    # networks while building this test) taken far longer than
    # Terraform/GCP's own wait period to actually release, even well
    # after the last real consumer (Cloud SQL) is confirmed gone. Rather
    # than keep retrying destroy indefinitely, this override sets
    # deletion_policy = "ABANDON" on just that one resource, scoped to
    # this test only (via Terraform's override-file mechanism, which
    # supports overriding regular arguments like this -- unlike
    # depends_on, which override files cannot touch at all). ABANDON
    # means Terraform stops tracking/managing the resource on destroy
    # without attempting the underlying API delete call -- appropriate
    # for a throwaway test resource, but deliberately NOT the shared
    # generator's default, since a real deployment tearing down
    # infrastructure should actually delete it, not abandon it.
    network_module_directory = workspace / "modules" / "network"
    (
        network_module_directory / "psa_deletion_policy_override.tf"
    ).write_text(
        'resource "google_service_networking_connection" '
        '"private_service_access" {\n'
        '  deletion_policy = "ABANDON"\n'
        "}\n",
        encoding="utf-8",
    )

    return workspace


@pytest.fixture(scope="module")
def live_var_file(
    crcs_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = crcs_live_workspace / "terraform.tfvars.example"
    live_file = crcs_live_workspace / "terraform.live.tfvars"

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

    live_file.write_text(content, encoding="utf-8")

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def crcs_live_runner(
    crcs_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the assembled workspace, with a
    substantially longer timeout given the network -> Cloud SQL
    sequential dependency inside a single apply."""

    factory_runner = terraform_runner_factory(crcs_live_workspace)

    return TerraformRunner(
        working_directory=crcs_live_workspace,
        terraform_binary=factory_runner.terraform_binary,
        timeout_seconds=2400,
    )


def test_crcs_live_apply_verify_and_destroy(
    crcs_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
) -> None:
    """Deploy, verify, and destroy the real composed platform."""

    plan_file = crcs_live_runner.working_directory / "crcs-live-e2e.tfplan"

    secret_address = (
        f'module.secret_manager.google_secret_manager_secret.this'
        f'["{live_names["database_secret_id"]}"]'
    )
    secret_version_address = (
        "google_secret_manager_secret_version.test_placeholder"
    )

    expected_addresses = {
        NETWORK_ADDRESS,
        SUBNET_ADDRESS,
        PSA_RANGE_ADDRESS,
        PSA_CONNECTION_ADDRESS,
        VPC_CONNECTOR_ADDRESS,
        CLOUD_SQL_INSTANCE_ADDRESS,
        CLOUD_SQL_DATABASE_ADDRESS,
        secret_address,
        secret_version_address,
        SERVICE_ACCOUNT_ADDRESS,
        CLOUD_RUN_SERVICE_ADDRESS,
        CLOUD_SQL_CLIENT_ADDRESS,
        SECRET_ACCESS_ADDRESS,
    }

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = crcs_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = crcs_live_runner.validate()
        assert validate_result.succeeded

        plan_result = crcs_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = crcs_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert expected_addresses.issubset(resource_addresses)

        # This is the slow part: the network's PSA connection and VPC
        # connector must finish before Cloud SQL can even start
        # creating, all inside this one apply.
        #
        # Two-phase apply, not the single saved plan_result.plan_file:
        # Cloud Run's DB_PASSWORD reference needs a real secret VERSION
        # to exist before it can be created (this architecture
        # deliberately generates the secret container only, not a
        # version -- see the crcs_live_workspace fixture). Phase one
        # creates just the secret and its placeholder version; phase
        # two is a fresh inline apply of everything else, since the
        # original saved plan is now stale against the changed state.
        secret_phase_result = crcs_live_runner._run(
            [
                "apply",
                "-no-color",
                "-input=false",
                "-auto-approve",
                "-var-file",
                str(live_var_file),
                "-target=module.secret_manager",
                "-target=google_secret_manager_secret_version.test_placeholder",
            ]
        )
        assert secret_phase_result.succeeded

        apply_result = crcs_live_runner.apply(var_file=live_var_file)

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(crcs_live_runner.state_list())

        assert expected_addresses.issubset(state_resources)

        outputs = crcs_live_runner.output_json()

        assert "cloud_run_service_uri" in outputs
        assert "cloud_run_runtime_service_account_email" in outputs
        assert "cloud_sql_connection_name" in outputs
        assert "network_id" in outputs
        assert "vpc_connector_id" in outputs
        assert "database_secret_id" in outputs

        assert outputs["database_secret_id"].get("value") == (
            live_names["database_secret_id"]
        )

        cloud_sql_connection_name = outputs["cloud_sql_connection_name"].get(
            "value"
        )
        assert cloud_sql_connection_name
        assert cloud_sql_connection_name.endswith(
            f":{live_names['service_name']}-db"
        )

        # The wiring itself is already meaningfully proven by this point:
        # `module.cloud_run.cloud_sql_instances` references
        # `module.cloud_sql.connection_name` directly in the root
        # template, and a broken cross-module reference would have
        # failed plan/apply outright rather than silently succeeding. A
        # deeper check against Cloud Run v2's own internal state JSON
        # shape (template/vpc_access/volumes nesting) was deliberately
        # left out here: guessing at that schema without a real
        # deployment to verify it against risks a false failure on
        # correctly-wired infrastructure.

        vpc_connector_id = outputs["vpc_connector_id"].get("value")
        assert vpc_connector_id
        assert live_names["network_name"] in vpc_connector_id

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(crcs_live_runner.state_list())

            if apply_completed or (expected_addresses & state_resources):
                # Retry with backoff, not a single destroy call: this
                # project's servicenetworking peering has consistently
                # (5 for 5 runs while building this test) taken far
                # longer than Google's own API wait period to actually
                # release, failing with "Producer services ... are
                # still using this connection" even though the last
                # real consumer (Cloud SQL) is already confirmed gone.
                # Retrying the same destroy command is safe and
                # idempotent -- Terraform only re-attempts whatever
                # remains in state, which is fast once the bulk of
                # resources are already destroyed.
                destroy_backoffs_seconds = (0, 60, 180, 300, 600)
                last_destroy_error: BaseException | None = None

                for attempt, wait_seconds in enumerate(
                    destroy_backoffs_seconds
                ):
                    if wait_seconds:
                        time.sleep(wait_seconds)

                    try:
                        destroy_result = crcs_live_runner.destroy(
                            var_file=live_var_file,
                        )

                        assert destroy_result.succeeded
                        assert (
                            "Destroy complete!"
                            in destroy_result.combined_output
                        )

                        last_destroy_error = None
                        break

                    except BaseException as error:
                        last_destroy_error = error
                        print(
                            f"\nDestroy attempt {attempt + 1}/"
                            f"{len(destroy_backoffs_seconds)} failed, "
                            f"{'retrying' if attempt + 1 < len(destroy_backoffs_seconds) else 'giving up'}"
                            f": {error}"
                        )

                if last_destroy_error is not None:
                    raise last_destroy_error

                remaining_resources = set(crcs_live_runner.state_list())

                assert not (expected_addresses & remaining_resources)

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"\nLive Cloud Run + Cloud SQL E2E test took "
        f"{elapsed_seconds:.1f}s (apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Run + Cloud SQL E2E test failed and cleanup "
            f"also failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Cloud Run + Cloud SQL E2E infrastructure "
            "verification passed, but Terraform cleanup failed. Since "
            "this creates real, billable resources (including a Cloud "
            "SQL instance), check the GCP Console to confirm nothing "
            "was left behind, and re-run `terraform destroy` directly "
            f"in the workspace ({crcs_live_runner.working_directory}) "
            "if needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

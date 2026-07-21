"""Live end-to-end test for the assembled BigQuery + Pub/Sub + Cloud
Functions event pipeline.

This test assembles the composed pipeline (via
`assemble_bigquery_pubsub_pipeline`, which writes the full multi-module
workspace directly to `generated/<workspace_name>/`), deploys it for
real, verifies the cross-module wiring actually works end to end
(publishing a real message and confirming it lands in BigQuery), and
always destroys everything during cleanup -- even if an earlier
assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

Unlike the standalone generator live tests, this fixture does not
manually call a generator and write files itself: the assembler function
already writes the complete workspace (root files plus
`modules/pubsub`, `modules/cloud-functions`, `modules/bigquery`) directly
to disk, so the fixture just needs to call it once and patch the real
project ID into the generated tfvars.

**Real, functional verification, not just "did resources get created."**
This test also publishes an actual test message to the generated Pub/Sub
topic and polls the generated BigQuery table for the resulting row --
proving the Eventarc trigger, the function's own IAM grants, and the
function's BigQuery write permission all genuinely work together, not
just that Terraform's plan matched reality. This uses the `gcloud` and
`bq` CLIs directly (both already required for every other live test in
this session), not any new Python dependency.

One resource's address is only known after apply: the BigQuery dataset's
`editors` IAM binding is keyed by the function's runtime service account
email (`toset(var.editor_members)`), which is itself dynamic. This test
computes the expected email up front using the exact same
`substr("<function_name>-runtime", 0, 30)` truncation the generator
applies, so the address can still be predicted and asserted directly
rather than only checked by prefix.

Expect roughly 3-6 minutes for apply (similar order of magnitude to the
standalone Cloud Functions live test, since that's the slow part here
too), plus up to a couple of minutes of polling for the functional
message-to-BigQuery-row check.
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

from terraform_agent.intelligence.pipeline_assembler import (
    assemble_bigquery_pubsub_pipeline,
)

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "pipeline-live-e2e-test"

TOPIC_ADDRESS_TEMPLATE = 'module.pubsub.google_pubsub_topic.this["{topic}"]'
BUCKET_ADDRESS = "module.cloud_functions.google_storage_bucket.source"
OBJECT_ADDRESS = (
    "module.cloud_functions.google_storage_bucket_object.source_archive"
)
SERVICE_ACCOUNT_ADDRESS = "module.cloud_functions.google_service_account.runtime"
FUNCTION_ADDRESS = (
    "module.cloud_functions.google_cloudfunctions2_function.this"
)
TIME_SLEEP_ADDRESS = (
    "module.cloud_functions.time_sleep.wait_for_runtime_sa_propagation"
)
DATA_PROJECT_ADDRESS = "module.cloud_functions.data.google_project.this"
EVENTARC_RECEIVER_ADDRESS = (
    "module.cloud_functions.google_project_iam_member.eventarc_receiver[0]"
)
RUN_INVOKER_ADDRESS = (
    "module.cloud_functions.google_project_iam_member."
    "run_invoker_for_trigger[0]"
)
PUBSUB_TOKEN_CREATOR_ADDRESS = (
    "module.cloud_functions.google_service_account_iam_member."
    "pubsub_token_creator[0]"
)
DATASET_ADDRESS = "module.bigquery.google_bigquery_dataset.this"
TABLE_ADDRESS_TEMPLATE = (
    'module.bigquery.google_bigquery_table.this["{table}"]'
)

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid resource names for this test run."""

    suffix = uuid4().hex[:8]

    application = f"pipeline-e2e-{suffix}"

    return {
        "application": application,
        "topic_name": f"pipeline-e2e-{suffix}-events",
        "dataset_id": f"pipeline_e2e_{suffix}",
        "table_id": "events",
        "function_name": f"pipeline-e2e-{suffix}-proc",
        "source_bucket_name": f"pipeline-e2e-{suffix}-src",
    }


def compute_runtime_service_account_email(
    function_name: str, project_id: str
) -> str:
    """Compute the exact runtime service account email the generator will
    create, mirroring its own substr("<function_name>-runtime", 0, 30)
    truncation so this dynamic address can still be predicted directly.
    """

    account_id = f"{function_name}-runtime"[:30]

    return f"{account_id}@{project_id}.iam.gserviceaccount.com"


def create_deployable_source_archive(destination: Path) -> None:
    """Create a real deployable zip for the pipeline function.

    Ignores the incoming Pub/Sub message content entirely and always
    inserts a single row with a fresh UUID and the current timestamp --
    this keeps the functional check simple and independent of whatever
    payload the test happens to publish.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    main_py = """\
import os
import uuid
from datetime import datetime, timezone

import functions_framework
from google.cloud import bigquery


@functions_framework.cloud_event
def main(cloud_event):
    client = bigquery.Client()
    dataset = os.environ["BIGQUERY_DATASET"]
    table = os.environ["BIGQUERY_TABLE"]
    table_ref = f"{client.project}.{dataset}.{table}"

    row = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"BigQuery insert failed: {errors}")
"""

    requirements_txt = (
        "functions-framework==3.*\ngoogle-cloud-bigquery==3.*\n"
    )

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.py", main_py)
        archive.writestr("requirements.txt", requirements_txt)


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
        os.getenv("PIPELINE_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live pipeline test. "
            "Set PIPELINE_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a "
            "real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def pipeline_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Assemble the pipeline directly -- the assembler already writes
    the full workspace to generated/<workspace_name>/ on disk."""

    result = assemble_bigquery_pubsub_pipeline(
        workspace_name=WORKSPACE_NAME,
        region="asia-south1",
        environment="dev",
        owner="platform-team",
        application=live_names["application"],
        topic_name=live_names["topic_name"],
        dataset_id=live_names["dataset_id"],
        table_id=live_names["table_id"],
        function_name=live_names["function_name"],
        source_bucket_name=live_names["source_bucket_name"],
        # Deliberately overridden: the assembler defaults this to True
        # (the safe production default), which would block
        # `terraform destroy` during cleanup of this throwaway test
        # workspace.
        deletion_protection=False,
    )

    if result.get("stage") not in {"complete"}:
        pytest.fail(
            f"Pipeline assembly failed before file generation: {result}"
        )

    return repository_root / "generated" / WORKSPACE_NAME


@pytest.fixture(scope="module")
def live_source_archive(pipeline_live_workspace: Path) -> Path:
    """Create the real deployable zip referenced by terraform.tfvars."""

    archive_path = pipeline_live_workspace / "dist" / "function-source.zip"

    create_deployable_source_archive(archive_path)

    return archive_path


@pytest.fixture(scope="module")
def live_var_file(
    pipeline_live_workspace: Path,
    live_project_id: str,
    live_source_archive: Path,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = pipeline_live_workspace / "terraform.tfvars.example"
    live_file = pipeline_live_workspace / "terraform.live.tfvars"

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
def pipeline_live_runner(
    pipeline_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the assembled live pipeline
    workspace, with a longer timeout given Cloud Functions' build step."""

    factory_runner = terraform_runner_factory(pipeline_live_workspace)

    return TerraformRunner(
        working_directory=pipeline_live_workspace,
        terraform_binary=factory_runner.terraform_binary,
        timeout_seconds=900,
    )


def publish_test_message(topic_name: str, project_id: str) -> None:
    """Publish a single, trivial test message via the Pub/Sub client.

    Deliberately does not shell out to the `gcloud` CLI: it hit the same
    Windows subprocess/`.cmd`-resolution problem as the `bq` CLI did for
    the BigQuery query below (both ship as .cmd wrappers on Windows,
    which Python's subprocess.run cannot resolve without shell=True). The
    Pub/Sub Python client uses the same Application Default Credentials
    already configured for every other live test in this suite.
    """

    from google.cloud import pubsub_v1

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)

    future = publisher.publish(
        topic_path, b"pipeline-live-e2e-test-trigger"
    )
    future.result(timeout=30)


def query_bigquery_row_count(
    project_id: str, dataset_id: str, table_id: str
) -> int:
    """Return the current row count via the BigQuery Python client.

    Deliberately does not shell out to the `bq` CLI: on Windows, Python's
    subprocess.run cannot resolve `.cmd`-based CLI wrappers like `bq`
    without shell=True, and separately, `bq` itself can be broken by
    unrelated absl-py version conflicts on some machines (both were hit
    while building this test). The BigQuery Python client uses the same
    Application Default Credentials already configured for every other
    live test in this suite, sidestepping both problems entirely.
    """

    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)

    query_job = client.query(
        f"SELECT COUNT(*) AS row_count "
        f"FROM `{project_id}.{dataset_id}.{table_id}`"
    )

    rows = list(query_job.result())

    return int(rows[0].row_count)


def test_pipeline_live_apply_verify_and_destroy(
    pipeline_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
    live_project_id: str,
) -> None:
    """Deploy, functionally verify, and destroy the real event pipeline."""

    plan_file = pipeline_live_runner.working_directory / "pipeline-live-e2e.tfplan"

    topic_address = TOPIC_ADDRESS_TEMPLATE.format(
        topic=live_names["topic_name"]
    )
    table_address = TABLE_ADDRESS_TEMPLATE.format(
        table=live_names["table_id"]
    )
    expected_sa_email = compute_runtime_service_account_email(
        live_names["function_name"], live_project_id
    )
    editors_address = (
        "module.bigquery.google_bigquery_dataset_iam_member."
        f'editors["serviceAccount:{expected_sa_email}"]'
    )

    expected_addresses = {
        topic_address,
        BUCKET_ADDRESS,
        OBJECT_ADDRESS,
        SERVICE_ACCOUNT_ADDRESS,
        FUNCTION_ADDRESS,
        TIME_SLEEP_ADDRESS,
        DATA_PROJECT_ADDRESS,
        EVENTARC_RECEIVER_ADDRESS,
        RUN_INVOKER_ADDRESS,
        PUBSUB_TOKEN_CREATOR_ADDRESS,
        DATASET_ADDRESS,
        table_address,
        editors_address,
    }

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = pipeline_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = pipeline_live_runner.validate()
        assert validate_result.succeeded

        plan_result = pipeline_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = pipeline_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert expected_addresses.issubset(resource_addresses)

        # This is the slow part: the Cloud Function's real Cloud Build
        # step (now also installing google-cloud-bigquery).
        apply_result = pipeline_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(pipeline_live_runner.state_list())

        assert expected_addresses.issubset(state_resources)

        outputs = pipeline_live_runner.output_json()

        assert "topic_ids" in outputs
        assert "cloud_function_name" in outputs
        assert "bigquery_dataset_id" in outputs
        assert "bigquery_table_ids" in outputs

        assert (
            outputs["cloud_function_name"].get("value")
            == live_names["function_name"]
        )
        assert (
            outputs["bigquery_dataset_id"].get("value")
            == live_names["dataset_id"]
        )

        # Functional check: publish a real message and confirm it
        # produces a real row, proving the full wiring actually works.
        baseline_row_count = query_bigquery_row_count(
            project_id=live_project_id,
            dataset_id=live_names["dataset_id"],
            table_id=live_names["table_id"],
        )

        publish_test_message(
            topic_name=live_names["topic_name"],
            project_id=live_project_id,
        )

        row_count_increased = False

        for _ in range(12):
            time.sleep(10)
            current_row_count = query_bigquery_row_count(
                project_id=live_project_id,
                dataset_id=live_names["dataset_id"],
                table_id=live_names["table_id"],
            )
            if current_row_count > baseline_row_count:
                row_count_increased = True
                break

        assert row_count_increased, (
            "Published a test message but no new row appeared in "
            f"{live_names['dataset_id']}.{live_names['table_id']} after "
            "2 minutes of polling. The infrastructure/IAM assertions "
            "above already passed, so this specifically means the "
            "Eventarc trigger -> function -> BigQuery write path isn't "
            "actually working end to end, not that resources failed to "
            "create."
        )

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(pipeline_live_runner.state_list())

            if apply_completed or (expected_addresses & state_resources):
                destroy_result = pipeline_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    pipeline_live_runner.state_list()
                )

                assert not (expected_addresses & remaining_resources)

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"\nLive pipeline E2E test took {elapsed_seconds:.1f}s "
        "(apply + functional check + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live pipeline E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live pipeline E2E functional verification passed, but "
            "Terraform cleanup failed. Since this creates real, "
            "billable resources, check the GCP Console to confirm "
            "nothing was left behind, and re-run `terraform destroy` "
            "directly in the workspace "
            f"({pipeline_live_runner.working_directory}) if needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

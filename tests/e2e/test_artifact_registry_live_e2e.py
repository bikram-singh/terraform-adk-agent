"""Live end-to-end test for the standalone Artifact Registry generator.

This test generates the workspace directly from the ArtifactRegistryGenerator
(not composed via an assembler -- Artifact Registry is a standalone
generator), deploys it for real, verifies the repository via Terraform
state, and always destroys everything during cleanup -- even if an
earlier assertion fails.

reader_members/writer_members are deliberately left empty for this live
test: granting a real IAM binding would need a principal guaranteed to
exist in the target project, and no single service account is reliably
present across every GCP project (the App Engine default service
account, for example, only exists if App Engine was ever enabled). The
IAM binding logic itself is already thoroughly covered by this
generator's unit tests (validates rejection of public members, correct
role assignment, and correct HCL rendering for both empty and non-empty
member lists), so this live test focuses on the genuinely novel part:
proving the repository resource itself deploys correctly against real
GCP.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

Unlike GKE or the composed architectures, this generator has no
networking dependency, no known GCP capacity/quota quirks, and no
deletion_protection-style blocker on the repository resource itself, so
this is expected to be one of the fastest and simplest live tests in the
suite -- likely under a minute for apply and destroy combined.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from terraform_agent.generators.artifact_registry.generator import (
    ArtifactRegistryGenerator,
)
from terraform_agent.generators.base import GeneratorContext

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "artifact-registry-live-e2e-test"

REPOSITORY_ADDRESS = "google_artifact_registry_repository.this"

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


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
        os.getenv("ARTIFACT_REGISTRY_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live Artifact Registry "
            "test. Set ARTIFACT_REGISTRY_E2E_PROJECT_ID (or "
            "GOOGLE_CLOUD_PROJECT) to a real GCP project, for example "
            "your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    suffix = uuid4().hex[:6]

    return {
        "repository_id": f"ar-e2e-{suffix}",
    }


@pytest.fixture(scope="module")
def artifact_registry_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
    live_project_id: str,
) -> Path:
    """Generate the workspace directly via the generator -- Artifact
    Registry is a standalone generator, not a composed assembler."""

    generator = ArtifactRegistryGenerator()

    generated = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "repository_id": live_names["repository_id"],
                "format": "DOCKER",
                "description": "Live E2E test repository",
                "reader_members": [],
                "writer_members": [],
                # Dry run stays true even in the live test: proving the
                # cleanup policy actually deletes something would
                # require first creating and aging out real image
                # versions, which is out of scope here. The policy
                # resource itself is still created and verified.
                "enable_cleanup_policy": True,
                "cleanup_policy_keep_count": 10,
                "cleanup_policy_dry_run": True,
                "environment": "e2e",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
            },
        )
    )

    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    for filename, content in generated.files.items():
        (workspace / filename).write_text(content, encoding="utf-8")

    return workspace


@pytest.fixture(scope="module")
def live_var_file(
    artifact_registry_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a live tfvars file with the real project ID."""

    live_file = artifact_registry_live_workspace / "terraform.live.tfvars"
    live_file.write_text(
        f'project_id = "{live_project_id}"\n', encoding="utf-8"
    )

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def artifact_registry_live_runner(
    artifact_registry_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated workspace. No
    extended timeout needed here -- unlike GKE or the composed
    architectures, a single repository resource with two IAM bindings
    is expected to apply and destroy quickly."""

    return terraform_runner_factory(artifact_registry_live_workspace)


def test_artifact_registry_live_apply_verify_and_destroy(
    artifact_registry_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
    live_project_id: str,
) -> None:
    """Deploy, verify, and destroy the real repository."""

    plan_file = (
        artifact_registry_live_runner.working_directory
        / "artifact-registry-live-e2e.tfplan"
    )

    expected_addresses = {
        REPOSITORY_ADDRESS,
    }

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    try:
        init_result = artifact_registry_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = artifact_registry_live_runner.validate()
        assert validate_result.succeeded

        plan_result = artifact_registry_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = artifact_registry_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert expected_addresses.issubset(resource_addresses)

        apply_result = artifact_registry_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(artifact_registry_live_runner.state_list())

        assert expected_addresses.issubset(state_resources)

        outputs = artifact_registry_live_runner.output_json()

        assert "repository_id" in outputs
        assert "repository_name" in outputs
        assert "repository_url" in outputs

        assert (
            outputs["repository_id"].get("value")
            == live_names["repository_id"]
        )
        assert live_names["repository_id"] in outputs["repository_name"].get(
            "value", ""
        )
        assert outputs["repository_url"].get("value") == (
            f"asia-south1-docker.pkg.dev/{live_project_id}/"
            f"{live_names['repository_id']}"
        )

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(artifact_registry_live_runner.state_list())

            if apply_completed or (expected_addresses & state_resources):
                destroy_result = artifact_registry_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    artifact_registry_live_runner.state_list()
                )

                assert not (expected_addresses & remaining_resources)

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live Artifact Registry E2E test failed and cleanup "
            f"also failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live Artifact Registry E2E verification passed, but "
            "Terraform cleanup failed. Check the GCP Console (or "
            "`gcloud artifacts repositories list`) to confirm nothing "
            "was left behind, and re-run `terraform destroy` directly "
            "in the workspace "
            f"({artifact_registry_live_runner.working_directory}) if "
            "needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

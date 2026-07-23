"""Live end-to-end test for the assembled GKE + Network + IAM Workload
Identity platform.

This test assembles the composed architecture (via
`assemble_gke_workload_identity_platform`, which writes the full
multi-module workspace directly to `generated/<workspace_name>/`),
deploys it for real, verifies the cross-module wiring, and always
destroys everything during cleanup -- even if an earlier assertion
fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

This composition reuses the exact hand-written network + firewall setup
already proven correct while building the standalone GKE live E2E test,
so those specific lessons (custom-mode VPCs get no firewall rules
automatically, GKE private clusters need specific ones) don't need to be
relearned here. Two lessons from that same effort DO need to be
reapplied, since the shared assembler's `region` value is passed
straight through to the GKE module's `location`, which would otherwise
make this cluster regional (spanning every zone in the region) rather
than zonal:

- **Zone pinning**: a regional cluster needs capacity in every zone of
  the region simultaneously; a real, confirmed `GCE_STOCKOUT` in one
  zone was enough to fail the standalone GKE cluster's creation
  repeatedly until it was pinned to a single zone. The same override
  is applied here, to the same zone that worked before.
- **Node disk type**: the generator hardcodes `disk_type = "pd-balanced"`
  (SSD-backed), which drew on quota already exhausted elsewhere during
  the standalone GKE test. Overridden to `pd-standard` defensively here
  too, even though this project's SSD quota may have changed since.

Also new to this composition specifically: `gke_deletion_protection` was
missing from the assembler entirely (defaulting to the safe `True` with
no way to override) until this test surfaced it -- fixed properly in
`gke_platform_assembler.py` itself, not just patched here.

This test verifies real infrastructure and cross-module wiring via
Terraform state/outputs -- specifically, that the IAM module's workload
service account is genuinely distinct from GKE's own node service
account, and that its Workload Identity binding (`roles/
iam.workloadIdentityUser`, scoped to the specific Kubernetes
ServiceAccount) is present in state exactly as configured. It does not
deploy an actual pod to exercise the binding end-to-end (that would
require a real container image and Kubernetes manifests, out of scope
here), matching the same infra-only verification scope the standalone
GKE live test used.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest

from terraform_agent.intelligence.gke_platform_assembler import (
    assemble_gke_workload_identity_platform,
)

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "gke-platform-live-e2e-test"

# The exact zone that worked in the standalone GKE live test, after two
# earlier zones (us-central1-f, us-central1-c) both hit real
# GCE_STOCKOUT errors. Region is deliberately us-central1 here too,
# matching that same confirmed-working combination, rather than
# asia-south1 (which had its own separate, unresolved stockout pattern
# during that same effort).
LIVE_REGION = "us-central1"
LIVE_ZONE = "us-central1-a"

NETWORK_ADDRESS = "google_compute_network.this"
SUBNET_ADDRESS = "google_compute_subnetwork.this"
FIREWALL_INTERNAL_ADDRESS = "google_compute_firewall.allow_internal"
FIREWALL_MASTER_ADDRESS = "google_compute_firewall.allow_master_webhooks"

CLUSTER_ADDRESS = "module.gke.google_container_cluster.standard[0]"
NODE_POOL_ADDRESS = "module.gke.google_container_node_pool.primary[0]"
NODE_SERVICE_ACCOUNT_ADDRESS = "module.gke.google_service_account.nodes"
ARTIFACT_REGISTRY_ADDRESS = (
    "module.gke.google_artifact_registry_repository.images[0]"
)
NODE_ROLE_ADDRESSES = {
    'module.gke.google_project_iam_member.node_roles["roles/logging.logWriter"]',
    'module.gke.google_project_iam_member.node_roles["roles/monitoring.metricWriter"]',
    'module.gke.google_project_iam_member.node_roles["roles/monitoring.viewer"]',
    'module.gke.google_project_iam_member.node_roles["roles/stackdriver.resourceMetadata.writer"]',
    'module.gke.google_project_iam_member.node_roles["roles/artifactregistry.reader"]',
}

WORKLOAD_SERVICE_ACCOUNT_ADDRESS = "module.iam_workload.google_service_account.this"
WORKLOAD_RUNTIME_ROLE_ADDRESS = (
    'module.iam_workload.google_project_iam_member.runtime_roles'
    '["roles/logging.logWriter"]'
)

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid resource names for this test run."""

    suffix = uuid4().hex[:6]

    return {
        "network_name": f"gke-plat-e2e-{suffix}",
        "cluster_name": f"gke-plat-e2e-{suffix}",
        "workload_service_account_id": f"gke-plat-e2e-{suffix}-wl",
        "k8s_namespace": "default",
        "k8s_service_account": f"gke-plat-e2e-{suffix}-ksa",
    }


def compute_impersonator_member(
    project_id: str, k8s_namespace: str, k8s_service_account: str
) -> str:
    """Compute the exact impersonator member string the root template
    builds, mirroring its own interpolation so the dynamic-keyed
    for_each address can still be predicted directly."""

    return (
        f"serviceAccount:{project_id}.svc.id.goog"
        f"[{k8s_namespace}/{k8s_service_account}]"
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
    """Return the real GCP project ID used for this live test."""

    project_id = (
        os.getenv("GKE_PLATFORM_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live GKE platform test. "
            "Set GKE_PLATFORM_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) "
            "to a real GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def gke_platform_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Assemble the architecture directly -- the assembler already
    writes the full workspace to generated/<workspace_name>/ on disk."""

    result = assemble_gke_workload_identity_platform(
        workspace_name=WORKSPACE_NAME,
        region=LIVE_REGION,
        environment="dev",
        owner="platform-team",
        application=live_names["network_name"],
        network_name=live_names["network_name"],
        cluster_name=live_names["cluster_name"],
        # Sized down to keep this as fast/cheap as a GKE live test can
        # realistically be, matching the standalone GKE live test.
        node_machine_type="e2-medium",
        node_min_count=1,
        node_max_count=1,
        workload_service_account_id=live_names["workload_service_account_id"],
        k8s_namespace=live_names["k8s_namespace"],
        k8s_service_account=live_names["k8s_service_account"],
        # Deliberately overridden: the assembler defaults this to True
        # (the safe production default), which would block
        # `terraform destroy` during cleanup of this throwaway test
        # workspace.
        gke_deletion_protection=False,
    )

    if result.get("stage") != "complete":
        pytest.fail(
            f"Architecture assembly failed before file generation: "
            f"{result}"
        )

    workspace = repository_root / "generated" / WORKSPACE_NAME

    # Two overrides, both scoped to modules/gke/ only, both reapplying
    # real lessons from the standalone GKE live test (see this file's
    # module docstring for why): pin to a single zone instead of the
    # whole region, and use pd-standard instead of the generator's
    # default pd-balanced (SSD-backed) disk type.
    gke_module_directory = workspace / "modules" / "gke"
    # NOTE: node_config is a nested block. Terraform override files
    # replace nested blocks wholesale, not merge them attribute-by-
    # attribute -- so the full block is reproduced here (matching
    # modules/gke/node_pool.tf exactly) with only disk_type changed.
    # Dropping this and overriding just disk_type would have silently
    # discarded service_account, oauth_scopes, shielded_instance_config,
    # and workload_metadata_config, breaking the Workload Identity chain
    # entirely.
    (gke_module_directory / "live_test_override.tf").write_text(
        f'''
resource "google_container_cluster" "standard" {{
  location = "{LIVE_ZONE}"
}}

resource "google_container_cluster" "autopilot" {{
  location = "{LIVE_ZONE}"
}}

resource "google_container_node_pool" "primary" {{
  location = "{LIVE_ZONE}"

  node_config {{
    machine_type    = var.node_machine_type
    disk_size_gb    = var.node_disk_size_gb
    disk_type       = "pd-standard"
    spot            = var.node_spot
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    shielded_instance_config {{
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }}

    workload_metadata_config {{
      mode = "GKE_METADATA"
    }}

    labels = local.common_labels

    metadata = {{
      disable-legacy-endpoints = "true"
    }}
  }}
}}
''',
        encoding="utf-8",
    )

    return workspace


@pytest.fixture(scope="module")
def live_var_file(
    gke_platform_live_workspace: Path,
    live_project_id: str,
) -> Path:
    """Create a temporary tfvars file with the real project ID."""

    example_file = gke_platform_live_workspace / "terraform.tfvars.example"
    live_file = gke_platform_live_workspace / "terraform.live.tfvars"

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
def gke_platform_live_runner(
    gke_platform_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the assembled workspace, with a
    substantially longer timeout given GKE cluster creation/deletion
    time, matching the standalone GKE live test's own lesson."""

    factory_runner = terraform_runner_factory(gke_platform_live_workspace)

    return TerraformRunner(
        working_directory=gke_platform_live_workspace,
        terraform_binary=factory_runner.terraform_binary,
        timeout_seconds=2400,
    )


def test_gke_platform_live_apply_verify_and_destroy(
    gke_platform_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
    live_project_id: str,
) -> None:
    """Deploy, verify, and destroy the real composed platform."""

    plan_file = (
        gke_platform_live_runner.working_directory
        / "gke-platform-live-e2e.tfplan"
    )

    impersonator_member = compute_impersonator_member(
        project_id=live_project_id,
        k8s_namespace=live_names["k8s_namespace"],
        k8s_service_account=live_names["k8s_service_account"],
    )
    impersonation_address = (
        "module.iam_workload.google_service_account_iam_member."
        f'impersonators["{impersonator_member}"]'
    )

    expected_addresses = {
        NETWORK_ADDRESS,
        SUBNET_ADDRESS,
        FIREWALL_INTERNAL_ADDRESS,
        FIREWALL_MASTER_ADDRESS,
        CLUSTER_ADDRESS,
        NODE_POOL_ADDRESS,
        NODE_SERVICE_ACCOUNT_ADDRESS,
        ARTIFACT_REGISTRY_ADDRESS,
        WORKLOAD_SERVICE_ACCOUNT_ADDRESS,
        WORKLOAD_RUNTIME_ROLE_ADDRESS,
        impersonation_address,
        *NODE_ROLE_ADDRESSES,
    }

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = gke_platform_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = gke_platform_live_runner.validate()
        assert validate_result.succeeded

        plan_result = gke_platform_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = gke_platform_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert expected_addresses.issubset(resource_addresses)

        # This is the slow part: GKE cluster + node pool creation
        # typically takes several minutes regardless of node size, the
        # same lesson from the standalone GKE live test.
        apply_result = gke_platform_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(gke_platform_live_runner.state_list())

        assert expected_addresses.issubset(state_resources)

        outputs = gke_platform_live_runner.output_json()

        assert "cluster_name" in outputs
        assert "cluster_mode" in outputs
        assert "gke_workload_identity_pool" in outputs
        assert "node_service_account_email" in outputs
        assert "workload_service_account_email" in outputs

        assert (
            outputs["cluster_name"].get("value")
            == live_names["cluster_name"]
        )
        assert outputs["cluster_mode"].get("value") == "STANDARD"

        node_service_account_email = outputs[
            "node_service_account_email"
        ].get("value")
        workload_service_account_email = outputs[
            "workload_service_account_email"
        ].get("value")

        assert node_service_account_email
        assert workload_service_account_email

        # The real point of this composition: the workload service
        # account must be genuinely distinct from GKE's own node
        # service account, not accidentally the same identity.
        assert node_service_account_email != workload_service_account_email
        assert live_names["workload_service_account_id"] in (
            workload_service_account_email
        )

        # Confirm the actual Workload Identity binding took effect, not
        # just that the service account exists: the impersonation
        # resource's own member/role must match what was configured.
        state_json = gke_platform_live_runner.show_json()

        flattened_resources = []
        for module in (
            state_json.get("values", {})
            .get("root_module", {})
            .get("child_modules", [])
        ):
            flattened_resources.extend(module.get("resources", []))
            for nested in module.get("child_modules", []):
                flattened_resources.extend(nested.get("resources", []))

        matching_impersonation_resources = [
            resource
            for resource in flattened_resources
            if resource.get("address") == impersonation_address
        ]

        assert len(matching_impersonation_resources) == 1

        impersonation_values = matching_impersonation_resources[0].get(
            "values", {}
        )

        assert (
            impersonation_values.get("role")
            == "roles/iam.workloadIdentityUser"
        )
        assert impersonation_values.get("member") == impersonator_member

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(gke_platform_live_runner.state_list())

            if apply_completed or (
                expected_addresses & state_resources
            ):
                # Also the slow part in reverse: cluster + node pool
                # teardown typically takes several minutes too.
                destroy_result = gke_platform_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(
                    gke_platform_live_runner.state_list()
                )

                assert not (expected_addresses & remaining_resources)

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"\nLive GKE platform E2E test took {elapsed_seconds:.1f}s "
        "(apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live GKE platform E2E test failed and cleanup also "
            f"failed.\n\nTest failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live GKE platform E2E infrastructure verification "
            "passed, but Terraform cleanup failed. Since this creates "
            "a real, billable GKE cluster, check the GCP Console (or "
            "`gcloud container clusters list`) to confirm nothing was "
            "left behind, and re-run `terraform destroy` directly in "
            f"the workspace ({gke_platform_live_runner.working_directory}) "
            "if needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

"""Live end-to-end test for a generated GKE Terraform project.

This test creates a real GKE Standard cluster and node pool -- along with
a small, self-contained VPC-native network and subnet to satisfy GKE's
networking prerequisites -- verifies them against live Terraform/GCP
state, and always destroys everything during cleanup, even if an earlier
assertion fails.

The test is skipped unless both TERRAFORM_E2E_LIVE=true and
TERRAFORM_ALLOW_APPLY=true are set, matching the double-flag safety gate
used by every other live test in this suite.

**This is the most expensive and slowest live test in this whole suite.**
GKE cluster and node pool creation typically takes 5-10+ minutes, with
similar teardown time, and it bills hourly for real compute the entire
time it exists. Realistic expectation: 15-25 minutes end to end. Do not
interrupt a run in progress -- an interrupted apply/destroy here is the
scenario most likely to leave real, billable compute behind.

**Self-contained networking, chosen deliberately over touching real
project infrastructure.** Unlike Cloud SQL (which points at an existing
VPC with Private Service Access already configured), this test provisions
its own tiny VPC-native network and subnet -- with the two secondary IP
ranges GKE requires for pods and services -- as part of the same
Terraform apply that creates the cluster, and tears all of it down
afterward. This was a deliberate choice (discussed and confirmed before
building this test) to avoid making any permanent change to real project
networking just to run a test. Unlike Private Service Access peering,
plain network/subnet creation is fast (seconds, not minutes), so this
adds negligible time compared to the cluster itself.

The network/subnet resources are defined in a hand-written
`network_prerequisites.tf` file added alongside the generator's own
output. Cluster resources reference the network/subnetwork by a
deterministic, precomputed self-link string (not a live Terraform
reference), since GKE's `network`/`subnetwork` variables are plain
strings. To ensure Terraform creates the network before attempting the
cluster, a separate `gke_dependencies_override.tf` file uses Terraform's
built-in override-file mechanism to merge an explicit `depends_on` into
the generator's own `google_container_cluster` resources, without ever
modifying the generated file itself.

To keep this as fast and cheap as a GKE live test can realistically be,
several defaults are sized down: `node_machine_type` (e2-medium instead of
e2-standard-4), `node_min_count`/`node_max_count` pinned to 1 (no
autoscaling), a smaller node disk, and `create_artifact_registry` disabled
(one fewer resource to create/verify/destroy).
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
from terraform_agent.generators.gke.generator import GKEGenerator

from .terraform_runner import TerraformRunner


WORKSPACE_NAME = "gke-live-e2e-test"

NETWORK_ADDRESS = "google_compute_network.prereq"
SUBNET_ADDRESS = "google_compute_subnetwork.prereq"
INTERNAL_FIREWALL_ADDRESS = "google_compute_firewall.allow_internal"
MASTER_FIREWALL_ADDRESS = "google_compute_firewall.allow_master_webhooks"
CLUSTER_ADDRESS = "google_container_cluster.standard[0]"
NODE_POOL_ADDRESS = "google_container_node_pool.primary[0]"
SERVICE_ACCOUNT_ADDRESS = "google_service_account.nodes"

NODE_ROLE_ADDRESSES = {
    'google_project_iam_member.node_roles["roles/logging.logWriter"]',
    'google_project_iam_member.node_roles["roles/monitoring.metricWriter"]',
    'google_project_iam_member.node_roles["roles/monitoring.viewer"]',
    'google_project_iam_member.node_roles["roles/stackdriver.resourceMetadata.writer"]',
    'google_project_iam_member.node_roles["roles/artifactregistry.reader"]',
}

EXPECTED_RESOURCE_ADDRESSES = {
    NETWORK_ADDRESS,
    SUBNET_ADDRESS,
    INTERNAL_FIREWALL_ADDRESS,
    MASTER_FIREWALL_ADDRESS,
    CLUSTER_ADDRESS,
    NODE_POOL_ADDRESS,
    SERVICE_ACCOUNT_ADDRESS,
    *NODE_ROLE_ADDRESSES,
}

PODS_RANGE_NAME = "gke-pods"
SERVICES_RANGE_NAME = "gke-services"

TRUE_VALUES = {"1", "true", "yes", "on"}


def environment_flag_enabled(name: str) -> bool:
    """Return whether an environment-variable feature flag is enabled."""

    return os.getenv(name, "").strip().lower() in TRUE_VALUES


def create_unique_names() -> dict[str, str]:
    """Create unique, valid names for this test run."""

    suffix = uuid4().hex[:6]

    network_name = f"gke-e2e-{suffix}"

    return {
        "network_name": network_name,
        "subnet_name": f"{network_name}-subnet",
        "cluster_name": f"gke-e2e-{suffix}",
    }


def build_network_prerequisites_tf() -> str:
    """Return the hand-written network + subnet Terraform, secondary IP
    ranges included, sized to satisfy GKE's private-node requirements
    (Private Google Access enabled since NAT is not provisioned).

    Also includes firewall rules that a custom-mode VPC does NOT get
    automatically (unlike the `default` network, which has built-in
    "allow internal" rules). GKE private clusters specifically require
    the control plane to reach nodes on certain ports for webhooks/
    admission controllers, and nodes need to reach each other. Without
    these, node instances can repeatedly fail health checks -- which can
    surface as confusing, unrelated-looking errors (including
    quota-shaped ones) rather than a clear "nodes never became healthy"
    message. This was diagnosed by creating an equivalent cluster
    directly via gcloud CLI on the `default` network (which succeeded
    immediately), isolating the difference to the custom VPC's missing
    firewall rules.
    """

    return """
resource "google_compute_network" "prereq" {
  project                 = var.project_id
  name                    = var.network_name
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "prereq" {
  project                  = var.project_id
  name                     = var.subnet_name
  region                   = var.region
  network                  = google_compute_network.prereq.id
  ip_cidr_range            = "10.90.0.0/22"
  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.92.0.0/16"
  }

  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.96.0.0/20"
  }
}

resource "google_compute_firewall" "allow_internal" {
  project   = var.project_id
  name      = "${var.network_name}-allow-internal"
  network   = google_compute_network.prereq.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = [
    "10.90.0.0/22",
    "10.92.0.0/16",
    "10.96.0.0/20",
  ]
}

resource "google_compute_firewall" "allow_master_webhooks" {
  project   = var.project_id
  name      = "${var.network_name}-allow-master"
  network   = google_compute_network.prereq.id
  direction = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["443", "8443", "9443", "10250", "15017"]
  }

  source_ranges = [var.master_ipv4_cidr_block]
}
"""


def build_network_prerequisite_variables_tf() -> str:
    """Return variable declarations for the hand-written prerequisites."""

    return """
variable "network_name" {
  description = "Name for the ephemeral prerequisite VPC network."
  type        = string
}

variable "subnet_name" {
  description = "Name for the ephemeral prerequisite subnet."
  type        = string
}
"""


ZONE = "us-central1-a"


def build_dependencies_override_tf() -> str:
    """Return an override.tf that points network/subnetwork at the real
    prerequisite resources, switches the node pool's disk type away from
    pd-balanced, and pins the cluster to a single zone -- without ever
    modifying the generated files themselves.

    Terraform's override-file mechanism explicitly forbids overriding
    `depends_on` ("The depends_on argument may not be overridden") --
    that was the first approach tried here and it fails at `terraform
    init` before touching any cloud resources. Overriding the `network`/
    `subnetwork` *arguments* themselves is both allowed and better: it
    replaces the plain `var.network`/`var.subnetwork` string references
    (which carry no dependency information) with real references to
    `google_compute_network.prereq`/`google_compute_subnetwork.prereq`,
    which gives Terraform a genuine implicit dependency edge.

    The node pool disk_type override exists for a different,
    project-specific reason: this generator hardcodes
    `disk_type = "pd-balanced"` (not even exposed as a variable), and
    pd-balanced is SSD-backed under the hood. `pd-standard` (HDD-backed,
    a different quota family) avoids drawing on that quota without
    touching the shared generator, since pd-balanced remains a
    perfectly reasonable default for real deployments elsewhere.

    The `location` override to a single zone exists because of a real,
    confirmed root cause: `location = var.region` (a region string, e.g.
    "us-central1") makes both the cluster and node pool REGIONAL,
    meaning GKE tries to place one node in *every* zone of that region
    simultaneously. Multiple live attempts failed with `GCE_STOCKOUT`
    ("does not have enough resources available") in different zones
    (us-central1-f, then us-central1-c) -- a real, temporary GCP capacity
    shortage, confirmed by checking `gcloud container operations
    describe` on the stuck operation. A regional cluster requires ALL
    zones in the region to have capacity at once; a zonal cluster (this
    override) only needs ONE zone's capacity, cutting stockout exposure
    roughly 3x for a 3-zone region. If ZONE below also turns out to be
    stocked out, trying a different zone in the same region is the
    reasonable next step -- this is inherent GCP capacity variance, not
    something any Terraform configuration can guarantee around.

    Terraform's override merge is per-attribute within a correlated
    nested block, so unrelated attributes (`machine_type`,
    `disk_size_gb`, `service_account`, etc.) are left untouched --
    only the specific overridden attributes change.
    """

    return f"""
resource "google_container_cluster" "standard" {{
  location   = "{ZONE}"
  network    = google_compute_network.prereq.name
  subnetwork = google_compute_subnetwork.prereq.name
}}

resource "google_container_cluster" "autopilot" {{
  location   = "{ZONE}"
  network    = google_compute_network.prereq.name
  subnetwork = google_compute_subnetwork.prereq.name
}}

resource "google_container_node_pool" "primary" {{
  location = "{ZONE}"

  node_config {{
    disk_type = "pd-standard"
  }}
}}
"""


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


def replace_tfvars_bool_value(
    content: str,
    variable_name: str,
    value: bool,
) -> str:
    """Replace an unquoted true/false value in Terraform tfvars content."""

    pattern = re.compile(
        rf'(?m)^(\s*{re.escape(variable_name)}\s*=\s*)(?:true|false)\s*$'
    )

    replacement = "true" if value else "false"

    updated_content, replacement_count = pattern.subn(
        rf'\1{replacement}',
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
    """Return the real GCP project ID used for live GKE testing."""

    project_id = (
        os.getenv("GKE_E2E_PROJECT_ID", "").strip()
        or os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    )

    if not project_id:
        pytest.fail(
            "No project ID configured for the live GKE test. "
            "Set GKE_E2E_PROJECT_ID (or GOOGLE_CLOUD_PROJECT) to a real "
            "GCP project, for example your nonprod project."
        )

    return project_id


@pytest.fixture(scope="module")
def live_names() -> dict[str, str]:
    """Return unique resource names for this test execution."""

    return create_unique_names()


@pytest.fixture(scope="module")
def gke_live_workspace(
    repository_root: Path,
    live_names: dict[str, str],
) -> Path:
    """Generate a fresh GKE workspace, plus hand-written network
    prerequisites and a dependency override file."""

    generator = GKEGenerator()

    project = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "us-central1",
                "cluster_name": live_names["cluster_name"],
                # NOTE: network, subnetwork, pods_secondary_range_name,
                # services_secondary_range_name, and
                # create_artifact_registry are NOT read by generator.py
                # at all -- they're static literals or bare Terraform
                # variables with no Python-side default injection, so
                # they must be set via tfvars instead (see live_var_file
                # below), not through GeneratorContext.
                #
                # Sized down to keep this as fast/cheap as a GKE live
                # test can realistically be.
                "node_machine_type": "e2-medium",
                "node_min_count": 1,
                "node_max_count": 1,
                "node_disk_size_gb": 30,
                # Deliberately overridden: the generator defaults this to
                # True, which would block `terraform destroy`.
                "deletion_protection": False,
                "environment": "dev",
                "owner": "platform-team",
                "application": "gke-live-e2e",
            },
        )
    )

    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    for name, content in project.files.items():
        (workspace / name).write_text(content, encoding="utf-8")

    (workspace / "network_prerequisites.tf").write_text(
        build_network_prerequisites_tf(), encoding="utf-8"
    )
    (workspace / "network_prerequisite_variables.tf").write_text(
        build_network_prerequisite_variables_tf(), encoding="utf-8"
    )
    (workspace / "gke_dependencies_override.tf").write_text(
        build_dependencies_override_tf(), encoding="utf-8"
    )

    return workspace


@pytest.fixture(scope="module")
def live_var_file(
    gke_live_workspace: Path,
    live_project_id: str,
    live_names: dict[str, str],
) -> Path:
    """Create a temporary tfvars file with the real project ID and the
    prerequisite network/subnet names."""

    example_file = gke_live_workspace / "terraform.tfvars.example"
    live_file = gke_live_workspace / "terraform.live.tfvars"

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

    # network/subnetwork are intentionally left as the generator's own
    # placeholder values. They're still required (no default), but the
    # cluster resources' actual network/subnetwork arguments are
    # overridden in gke_dependencies_override.tf to reference the real
    # google_compute_network.prereq/google_compute_subnetwork.prereq
    # resources directly -- so these tfvars values are never actually
    # used, just present to satisfy Terraform's "variable has no
    # default" requirement.

    # pods_secondary_range_name / services_secondary_range_name are also
    # left as-is: the generator's own placeholder values ("gke-pods" /
    # "gke-services") already match the secondary ranges defined in
    # network_prerequisites.tf.

    # create_artifact_registry, like network/subnetwork, is a static
    # literal in the generator's tfvars template (not Python-processed),
    # so it must also be overridden here rather than through
    # GeneratorContext to actually take effect.
    content = replace_tfvars_bool_value(
        content=content,
        variable_name="create_artifact_registry",
        value=False,
    )

    content += (
        f'\nnetwork_name = "{live_names["network_name"]}"\n'
        f'subnet_name  = "{live_names["subnet_name"]}"\n'
    )

    live_file.write_text(content, encoding="utf-8")

    yield live_file

    live_file.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def gke_live_runner(
    gke_live_workspace: Path,
    terraform_runner_factory: Callable[[Path], TerraformRunner],
) -> TerraformRunner:
    """Return a Terraform runner for the generated live GKE workspace.

    Deliberately does not use terraform_runner_factory's return value:
    that factory always builds a TerraformRunner with the shared 600s
    (10 minute) default timeout, which is far too short for GKE -- one
    real attempt during this test's development ran for over 35 minutes
    before GCP surfaced a GCE_STOCKOUT error. Requesting
    terraform_runner_factory as a fixture dependency still gets the
    "Terraform executable was not found" skip behavior for free (pytest
    resolves it regardless of whether its return value is used); this
    just constructs a second, longer-timeout runner for the actual
    apply/destroy calls.
    """

    return TerraformRunner(
        working_directory=gke_live_workspace,
        timeout_seconds=2400,
    )


def test_gke_live_apply_verify_and_destroy(
    gke_live_runner: TerraformRunner,
    live_var_file: Path,
    live_names: dict[str, str],
) -> None:
    """Deploy, verify, and destroy a real GKE cluster end to end."""

    plan_file = gke_live_runner.working_directory / "gke-live-e2e.tfplan"

    apply_completed = False
    test_error: BaseException | None = None
    cleanup_error: BaseException | None = None

    started_at = time.monotonic()

    try:
        init_result = gke_live_runner.init(backend=False)
        assert init_result.succeeded

        validate_result = gke_live_runner.validate()
        assert validate_result.succeeded

        plan_result = gke_live_runner.plan(
            var_file=live_var_file,
            plan_file=plan_file,
        )

        assert plan_result.command_result.return_code in (0, 2)
        assert plan_result.has_changes is True
        assert plan_result.plan_file is not None
        assert plan_result.plan_file.exists()

        plan_json = gke_live_runner.show_json(
            plan_file=plan_result.plan_file
        )

        resource_changes = plan_json.get("resource_changes", [])

        resource_addresses = {
            resource.get("address") for resource in resource_changes
        }

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(resource_addresses)

        cluster_changes = [
            resource
            for resource in resource_changes
            if resource.get("address") == CLUSTER_ADDRESS
        ]

        assert len(cluster_changes) == 1
        assert (
            cluster_changes[0].get("change", {}).get("actions", [])
            == ["create"]
        )

        # This is the slow part: GKE cluster + node pool creation
        # typically takes several minutes regardless of node size.
        apply_result = gke_live_runner.apply(
            plan_file=plan_result.plan_file
        )

        assert apply_result.succeeded
        assert "Apply complete!" in apply_result.combined_output

        apply_completed = True

        state_resources = set(gke_live_runner.state_list())

        assert EXPECTED_RESOURCE_ADDRESSES.issubset(state_resources)
        assert state_resources == EXPECTED_RESOURCE_ADDRESSES

        outputs = gke_live_runner.output_json()

        assert "cluster_name" in outputs
        assert "cluster_mode" in outputs
        assert "node_service_account_email" in outputs

        assert outputs["cluster_name"].get("value") == live_names[
            "cluster_name"
        ]
        assert outputs["cluster_mode"].get("value") == "STANDARD"
        assert outputs["node_service_account_email"].get("value")

        state_json = gke_live_runner.show_json()

        state_resources_json = (
            state_json.get("values", {})
            .get("root_module", {})
            .get("resources", [])
        )

        matching_cluster_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == CLUSTER_ADDRESS
        ]

        assert len(matching_cluster_resources) == 1

        cluster_values = matching_cluster_resources[0].get("values", {})

        assert cluster_values.get("name") == live_names["cluster_name"]
        assert cluster_values.get("deletion_protection") is False

        matching_node_pool_resources = [
            resource
            for resource in state_resources_json
            if resource.get("address") == NODE_POOL_ADDRESS
        ]

        assert len(matching_node_pool_resources) == 1

        node_pool_values = matching_node_pool_resources[0].get(
            "values", {}
        )

        node_config = node_pool_values.get("node_config", [])

        assert node_config
        assert node_config[0].get("machine_type") == "e2-medium"
        assert node_config[0].get("disk_type") == "pd-standard"

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

    except BaseException as error:
        test_error = error

    finally:
        try:
            state_resources = set(gke_live_runner.state_list())

            if apply_completed or (
                EXPECTED_RESOURCE_ADDRESSES & state_resources
            ):
                # Also the slow part in reverse: cluster + node pool
                # teardown typically takes several minutes as well.
                destroy_result = gke_live_runner.destroy(
                    var_file=live_var_file,
                )

                assert destroy_result.succeeded
                assert (
                    "Destroy complete!" in destroy_result.combined_output
                )

                remaining_resources = set(gke_live_runner.state_list())

                assert not (
                    EXPECTED_RESOURCE_ADDRESSES & remaining_resources
                )

        except BaseException as error:
            cleanup_error = error

        finally:
            plan_file.unlink(missing_ok=True)

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"\nLive GKE E2E test took {elapsed_seconds:.1f}s "
        "(apply + verify + destroy combined)."
    )

    if test_error is not None and cleanup_error is not None:
        raise AssertionError(
            "The live GKE E2E test failed and cleanup also failed.\n\n"
            f"Test failure:\n{test_error}\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from test_error

    if cleanup_error is not None:
        raise AssertionError(
            "The live GKE E2E infrastructure verification passed, but "
            "Terraform cleanup failed. Since this creates a real, "
            "billable GKE cluster, check the GCP Console (or "
            "`gcloud container clusters list`) to confirm nothing was "
            "left behind, and re-run `terraform destroy` directly in "
            f"the workspace ({gke_live_runner.working_directory}) if "
            "needed.\n\n"
            f"Cleanup failure:\n{cleanup_error}"
        ) from cleanup_error

    if test_error is not None:
        raise test_error

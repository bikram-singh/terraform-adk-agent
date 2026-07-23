"""Bounded cost estimation: rough monthly estimates for provisioned,
always-on resources in a generated workspace, using published GCP list
prices.

Deliberately does NOT call the real GCP Billing API and does NOT
attempt to estimate usage-based costs -- Cloud Run invocations,
BigQuery bytes scanned, Cloud Functions invocations, Pub/Sub message
volume, GCS storage/egress, or Artifact Registry storage all depend on
real traffic that can't be known from a Terraform plan or tfvars file
alone. This only estimates the resources that are billed by provisioned
capacity regardless of usage: Cloud SQL instances and GKE node pools
(plus the small GKE Standard control-plane fee).

Pricing is a static, hand-maintained table of published GCP list prices
for us-central1, verified against multiple independent, cited sources
as of PRICING_LAST_VERIFIED below -- not a live lookup. Real prices
vary by region (commonly 10-20% higher outside the US), change over
time, and don't reflect Sustained or Committed Use Discounts. Treat
every number here as a rough, order-of-magnitude estimate, and verify
anything decision-relevant against the real GCP Pricing Calculator.
"""

from __future__ import annotations

import re
from typing import Any

from terraform_agent.tools.policy_tools import parse_tfvars
from terraform_agent.tools.workspace_tools import get_workspace_path


PRICING_LAST_VERIFIED = "2026-07-23"
PRICING_REGION_BASIS = "us-central1"
HOURS_PER_MONTH = 730

# Compute Engine on-demand hourly rates (USD), by machine type. Also
# used for GKE Standard node pools, since GKE nodes are billed as
# ordinary Compute Engine VMs.
COMPUTE_ENGINE_HOURLY_RATES: dict[str, float] = {
    "e2-micro": 0.0084,
    "e2-small": 0.0168,
    "e2-medium": 0.0335,
    "e2-standard-2": 0.0670,
    "e2-standard-4": 0.1340,
    "e2-standard-8": 0.2680,
    "e2-standard-16": 0.5360,
}

# Cloud SQL Enterprise edition, dedicated-core, on-demand, zonal.
CLOUD_SQL_VCPU_HOURLY_RATE = 0.0413
CLOUD_SQL_MEMORY_GB_HOURLY_RATE = 0.0070
CLOUD_SQL_REGIONAL_MULTIPLIER = 2.0  # REGIONAL/HA roughly doubles compute cost.
CLOUD_SQL_SHARED_CORE_MONTHLY_RATES: dict[str, float] = {
    "db-f1-micro": 8.00,
    "db-g1-small": 27.00,
}

# GKE Standard mode's per-cluster management fee. One zonal cluster per
# billing account is free; every additional cluster (and every regional
# cluster) is billed at this rate. This estimator can't know how many
# other clusters exist on the same billing account, so it always shows
# this fee with that caveat rather than guessing whether it's waived.
GKE_STANDARD_CLUSTER_MANAGEMENT_HOURLY_RATE = 0.10

_CUSTOM_TIER_PATTERN = re.compile(r"^db-custom-(\d+)-(\d+)$")


def parse_cloud_sql_custom_tier(tier: str) -> tuple[int, int] | None:
    """Parse a `db-custom-<vcpu>-<memory_mb>` tier into (vcpu, memory_mb).
    Returns None for shared-core tiers (db-f1-micro, db-g1-small) or any
    tier this parser doesn't recognize."""

    match = _CUSTOM_TIER_PATTERN.match(tier.strip())
    if not match:
        return None

    return int(match.group(1)), int(match.group(2))


def estimate_cloud_sql_monthly_cost(
    tier: str, availability_type: str = "ZONAL"
) -> dict[str, Any]:
    """Estimate a Cloud SQL instance's monthly compute cost. Storage,
    backups, and network egress are not included -- those depend on
    real data volume."""

    tier = tier.strip()
    is_regional = availability_type.strip().upper() in (
        "REGIONAL",
        "HA",
    )

    if tier in CLOUD_SQL_SHARED_CORE_MONTHLY_RATES:
        monthly_cost = CLOUD_SQL_SHARED_CORE_MONTHLY_RATES[tier]
        if is_regional:
            monthly_cost *= CLOUD_SQL_REGIONAL_MULTIPLIER
        return {
            "status": "estimated",
            "resource": f"Cloud SQL instance ({tier})",
            "monthly_cost_usd": round(monthly_cost, 2),
            "notes": (
                "Shared-core tier flat rate. Excludes storage, backups, "
                "and network egress."
            ),
        }

    parsed = parse_cloud_sql_custom_tier(tier)
    if parsed is None:
        return {
            "status": "unknown_tier",
            "resource": f"Cloud SQL instance ({tier})",
            "monthly_cost_usd": None,
            "notes": (
                f"Unrecognized tier '{tier}'. Only db-custom-<vcpu>-"
                "<memory_mb>, db-f1-micro, and db-g1-small are "
                "supported by this estimator."
            ),
        }

    vcpu, memory_mb = parsed
    memory_gb = memory_mb / 1024

    hourly_cost = (
        vcpu * CLOUD_SQL_VCPU_HOURLY_RATE
        + memory_gb * CLOUD_SQL_MEMORY_GB_HOURLY_RATE
    )
    if is_regional:
        hourly_cost *= CLOUD_SQL_REGIONAL_MULTIPLIER

    monthly_cost = hourly_cost * HOURS_PER_MONTH

    return {
        "status": "estimated",
        "resource": f"Cloud SQL instance ({tier}, {availability_type})",
        "monthly_cost_usd": round(monthly_cost, 2),
        "notes": (
            f"{vcpu} vCPU + {memory_gb:.2f} GB memory, compute only. "
            "Excludes storage, backups, and network egress."
            + (
                " REGIONAL/HA roughly doubles compute cost versus ZONAL."
                if is_regional
                else ""
            )
        ),
    }


def estimate_compute_engine_monthly_cost(
    machine_type: str, instance_count: int = 1
) -> dict[str, Any]:
    """Estimate the monthly cost of one or more Compute Engine VMs of
    a given machine type (also used for GKE Standard node pools)."""

    machine_type = machine_type.strip()
    hourly_rate = COMPUTE_ENGINE_HOURLY_RATES.get(machine_type)

    if hourly_rate is None:
        return {
            "status": "unknown_machine_type",
            "resource": f"{instance_count}x {machine_type}",
            "monthly_cost_usd": None,
            "notes": (
                f"'{machine_type}' is not in this estimator's pricing "
                "table. Only common e2 machine types are supported "
                "today."
            ),
        }

    monthly_cost = hourly_rate * HOURS_PER_MONTH * instance_count

    return {
        "status": "estimated",
        "resource": f"{instance_count}x {machine_type}",
        "monthly_cost_usd": round(monthly_cost, 2),
        "notes": "Compute only. Excludes attached disk and network egress.",
    }


def estimate_gke_control_plane_monthly_cost() -> dict[str, Any]:
    """Estimate GKE Standard mode's per-cluster management fee."""

    monthly_cost = (
        GKE_STANDARD_CLUSTER_MANAGEMENT_HOURLY_RATE * HOURS_PER_MONTH
    )

    return {
        "status": "estimated",
        "resource": "GKE Standard cluster management fee",
        "monthly_cost_usd": round(monthly_cost, 2),
        "notes": (
            "One zonal cluster per billing account is free; this fee "
            "applies to every additional cluster and every regional "
            "cluster. This estimator can't know how many other "
            "clusters exist on the same billing account, so this line "
            "is always shown -- it may not actually apply if this is "
            "your one free zonal cluster."
        ),
    }


def estimate_workspace_cost(
    workspace_name: str,
    var_file: str = "terraform.tfvars.example",
) -> dict[str, Any]:
    """
    Produce a rough monthly cost estimate for a generated workspace's
    provisioned (always-on) resources, using published GCP list prices.

    Reads the workspace's tfvars file (like check_policy_compliance
    does) and auto-detects Cloud SQL and GKE sizing from well-known
    variable names, covering both standalone generator workspaces
    (tier, availability_type, node_machine_type, node_min_count) and
    the composed Cloud Run + Cloud SQL / GKE platform assembler
    workspaces (db_tier, db_availability_type). GKE Autopilot clusters
    are explicitly flagged as not estimable here, since Autopilot bills
    per-pod resource requests rather than per-node.

    This is not a substitute for the real GCP Pricing Calculator or
    Billing API: prices are approximate, region-basis is us-central1
    only, and usage-based services (Cloud Run, Cloud Functions,
    Pub/Sub, BigQuery, GCS, Artifact Registry, Secret Manager) are not
    estimated at all, since their real cost depends on traffic volume
    this tool has no way to know.
    """

    workspace = get_workspace_path(workspace_name)

    if not workspace.exists() or not workspace.is_dir():
        return {
            "status": "error",
            "message": f"Workspace does not exist: {workspace_name}",
        }

    var_file_path = (workspace / var_file).resolve()
    try:
        var_file_path.relative_to(workspace.resolve())
    except ValueError:
        return {
            "status": "error",
            "message": "Rejected var_file path outside the workspace.",
        }

    if not var_file_path.exists():
        return {
            "status": "error",
            "message": (
                f"'{var_file}' does not exist in workspace "
                f"'{workspace_name}'."
            ),
        }

    values = parse_tfvars(
        var_file_path.read_text(encoding="utf-8")
    )

    line_items: list[dict[str, Any]] = []
    not_estimated: list[str] = []

    tier = values.get("tier") or values.get("db_tier")
    if tier:
        availability_type = (
            values.get("availability_type")
            or values.get("db_availability_type")
            or "ZONAL"
        )
        line_items.append(
            estimate_cloud_sql_monthly_cost(tier, availability_type)
        )

    cluster_mode = (values.get("cluster_mode") or "").strip().upper()
    node_machine_type = values.get("node_machine_type")

    if cluster_mode == "AUTOPILOT":
        not_estimated.append(
            "GKE Autopilot cluster: bills per-pod resource requests, "
            "not per-node, so this estimator can't produce a "
            "meaningful node cost without knowing real workload sizes."
        )
    elif node_machine_type:
        node_min_count = values.get("node_min_count", "1")
        try:
            node_count = int(node_min_count)
        except ValueError:
            node_count = 1

        line_items.append(
            estimate_compute_engine_monthly_cost(
                node_machine_type, instance_count=node_count
            )
        )
        line_items.append(estimate_gke_control_plane_monthly_cost())

    vpc_connector_machine_type = values.get("vpc_connector_machine_type")
    if vpc_connector_machine_type:
        vpc_connector_min_instances = values.get(
            "vpc_connector_min_instances", "2"
        )
        try:
            connector_count = int(vpc_connector_min_instances)
        except ValueError:
            connector_count = 2

        line_items.append(
            estimate_compute_engine_monthly_cost(
                vpc_connector_machine_type,
                instance_count=connector_count,
            )
        )

    usage_based_indicators = {
        "service_name": "Cloud Run (usage-based: requests, CPU/memory-seconds)",
        "function_name": "Cloud Functions (usage-based: invocations, compute time)",
        "topics": "Pub/Sub (usage-based: message volume)",
        "dataset_id": "BigQuery (usage-based: storage, bytes scanned)",
        "bucket_name": "Cloud Storage (usage-based: storage, network egress)",
        "repository_id": "Artifact Registry (usage-based: storage)",
        "secret_ids": "Secret Manager (typically free-tier eligible at low volume)",
    }
    for key, description in usage_based_indicators.items():
        if key in values:
            not_estimated.append(description)

    estimated_items = [
        item for item in line_items if item["status"] == "estimated"
    ]
    unestimable_items = [
        item for item in line_items if item["status"] != "estimated"
    ]

    total_monthly_cost = round(
        sum(
            item["monthly_cost_usd"]
            for item in estimated_items
        ),
        2,
    )

    return {
        "status": "success",
        "workspace_name": workspace_name,
        "pricing_basis": {
            "region": PRICING_REGION_BASIS,
            "last_verified": PRICING_LAST_VERIFIED,
            "disclaimer": (
                "Approximate published list prices for us-central1, "
                "on-demand, no discounts applied. Real prices vary by "
                "region and change over time. Verify anything "
                "decision-relevant against the real GCP Pricing "
                "Calculator."
            ),
        },
        "estimated_monthly_cost_usd": total_monthly_cost,
        "line_items": line_items,
        "not_estimated": not_estimated,
        "message": (
            f"Estimated ~${total_monthly_cost:,.2f}/month for "
            f"{len(estimated_items)} provisioned resource(s)."
            + (
                f" {len(unestimable_items)} resource(s) could not be "
                "estimated."
                if unestimable_items
                else ""
            )
            + (
                f" {len(not_estimated)} usage-based service(s) present "
                "but not included in this estimate."
                if not_estimated
                else ""
            )
        ),
    }

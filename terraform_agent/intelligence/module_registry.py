"""Lightweight module registry: a single, queryable source of truth for
every standalone generator and composed architecture this agent can
build, including whether each has been proven against real GCP
infrastructure.

Combines the existing generator plugin registry (already tracked per
generator via ServiceMetadata) with the three composed architecture
recipes, which had no structured metadata anywhere until now -- only a
human-readable mention in STATUS.md.
"""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.registry import list_generator_metadata


# Live-verification status is tracked here explicitly rather than
# inferred, since "has this been proven against real GCP infrastructure"
# is a fact about testing history, not something derivable from the
# generator's own code. All ten standalone generators and all three
# composed architectures are live-verified as of this registry's
# creation; a newly added generator or recipe should default to False
# here until it actually is.
_LIVE_VERIFIED_GENERATORS: frozenset[str] = frozenset(
    {
        "artifact-registry",
        "bigquery",
        "cloud-functions",
        "cloud-run",
        "cloud-sql",
        "gcs",
        "gke",
        "iam",
        "network",
        "pubsub",
        "secret-manager",
    }
)

COMPOSED_ARCHITECTURES: tuple[dict[str, Any], ...] = (
    {
        "architecture_type": "private-cloud-run-cloud-sql",
        "display_name": "Private Cloud Run + Cloud SQL Platform",
        "description": (
            "A private Cloud Run service connected to a private Cloud "
            "SQL instance over Private Service Access, with Secret "
            "Manager holding the database credential reference."
        ),
        "composes_generators": (
            "network",
            "cloud-sql",
            "secret-manager",
            "cloud-run",
        ),
        "assembler_tool": "assemble_private_cloud_run_postgres_platform",
        "live_verified": True,
    },
    {
        "architecture_type": "bigquery-pubsub-cloud-functions-pipeline",
        "display_name": "BigQuery + Pub/Sub + Cloud Functions Event Pipeline",
        "description": (
            "An event-driven data pipeline: a Pub/Sub topic triggers a "
            "Cloud Function via its native event trigger (Eventarc "
            "managed automatically, no separate subscription), which "
            "writes into a BigQuery dataset and table."
        ),
        "composes_generators": ("pubsub", "cloud-functions", "bigquery"),
        "assembler_tool": "assemble_event_driven_data_pipeline",
        "live_verified": True,
        "notes": (
            "Does not generate the function's own application code; a "
            "zipped function source must be provided before deploying."
        ),
    },
    {
        "architecture_type": "gke-network-iam-workload-identity-platform",
        "display_name": "GKE + Network + IAM Workload Identity Platform",
        "description": (
            "A private, VPC-native GKE Standard cluster with its own "
            "node service account, plus a separate, dedicated "
            "application workload service account bound via Workload "
            "Identity Federation to a specific Kubernetes ServiceAccount."
        ),
        "composes_generators": ("gke", "iam"),
        "assembler_tool": "assemble_gke_platform",
        "live_verified": True,
    },
)


def list_available_modules() -> dict[str, Any]:
    """
    Return a single, structured inventory of every standalone generator
    and composed architecture this agent can build, including each
    one's live-verification status (whether it has actually been
    proven end-to-end against real GCP infrastructure, not just locally
    validated).
    """

    generators = tuple(
        {
            **entry,
            "live_verified": entry["service_name"]
            in _LIVE_VERIFIED_GENERATORS,
        }
        for entry in list_generator_metadata()
    )

    return {
        "status": "success",
        "standalone_generators": generators,
        "composed_architectures": COMPOSED_ARCHITECTURES,
        "standalone_generator_count": len(generators),
        "composed_architecture_count": len(COMPOSED_ARCHITECTURES),
        "message": (
            f"{len(generators)} standalone generator(s) and "
            f"{len(COMPOSED_ARCHITECTURES)} composed architecture "
            "recipe(s) available."
        ),
    }

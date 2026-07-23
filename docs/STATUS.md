# terraform-adk-agent — Status

_This is the canonical, up-to-date status doc for this project. Update this
file directly when things change — don't keep a separate copy elsewhere,
since that's exactly how the previous version of this table went stale._

Last verified: 2026-07-23

## Test Report

| Generator          | Generate | Validate | Plan | Apply | Destroy | Status |
|--------------------|:--------:|:--------:|:----:|:-----:|:-------:|--------|
| GCS                | ✅       | ✅       | ✅   | ✅    | ✅      | Completed |
| Secret Manager     | ✅       | ✅       | ✅   | ✅    | ✅      | Completed |
| IAM                | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 75s |
| Pub/Sub            | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 79s |
| BigQuery           | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 38s |
| Network (VPC)      | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 533s |
| Cloud Functions    | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 141s (2 real bugs fixed) |
| Cloud Run          | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 73s |
| Cloud SQL          | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 618s (1 real bug fixed) |
| GKE                | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 917s (2 real bugs + 3 environment issues fixed) |
| Artifact Registry  | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 32.96s |

**All 11 generators: fully complete.** Generate/Validate verified by unit
tests; Plan/Apply/Destroy verified by real `terraform` runs against a live
GCP project (`dhg-vaccine-rateauto-nonpord`), not just static analysis.

## Real bugs found and fixed in the generator codebase this cycle

These were genuine defects that would have affected any real user of these
generators, not test-environment quirks:

- **GKE**: `enable_components` used the invalid literal `API_SERVER`
  instead of the correct `APISERVER` — real cluster creation would always
  have failed on this.
- **GKE**: missing `master_authorized_networks_config` — any cluster with
  the generator's own default `enable_private_endpoint = true` would fail
  to create, since the GKE API requires this whenever the endpoint is
  private-only. Fixed with a new, validated `master_authorized_networks`
  variable (default `10.0.0.0/8`).
- **Cloud Functions**: `vpc_connector_egress_settings` was set
  unconditionally even when no `vpc_connector` was configured — every
  default deployment would fail with a real Cloud Run API rejection.
- **Cloud Functions**: no buffer for IAM propagation delay on the
  freshly-created runtime service account — intermittently caused
  `actAs` permission errors on real deployments. Fixed with a
  `time_sleep` resource.
- **Cloud SQL**: no explicit `edition` control — defaults to whatever the
  GCP project/account itself defaults to, which silently breaks
  `db-custom-*` tiers on any account defaulting to `ENTERPRISE_PLUS`.
  Fixed with an explicit, validated `edition` variable (default
  `ENTERPRISE`).
- **`terraform fmt` alignment bug (systemic, found and fixed this
  session)**: any list/map-typed variable's `default` line was always
  rendered with a fixed alignment, but `terraform fmt` aligns `=` signs
  differently depending on whether the actual value is single-line
  (`[]`/`{}`) or multi-line (any non-empty list/map) — no static template
  string can get this right in both cases at once. Root-caused with a
  shared `render_default_assignment()` helper (computes spacing from the
  real rendered value) rather than patched per-generator. Affected
  BigQuery, IAM, Network, Pub/Sub, Secret Manager, and the GKE platform
  assembler; fixed in all six, verified against real mixed empty/non-empty
  test cases in each.
- **NL→Terraform intent detection (real gap, found and fixed this
  session)**: `design_infrastructure_platform`'s natural-language
  detector (`detector.py`/`architect.py`) only ever recognized the
  private Cloud Run + Cloud SQL recipe — a request like "build an
  event-driven pipeline with Pub/Sub and BigQuery" would have been
  rejected as unsupported, even though the underlying assembler worked
  perfectly when called directly. Extended detection, the dependency
  graph builders, and the assembler dispatch to recognize and correctly
  route all three composed recipes; verified end-to-end by inspecting
  the real generated files for all three via natural-language requests.

## Roadmap — reconciled with what's actually shipped

```
v0.5    Plugin-based Multi-Service Generator Framework      ✅
v0.6    Cloud Run generator                                 ✅
v0.7    HashiCorp Terraform MCP Server integration (client)  ✅
v0.7.2  Terraform Registry MCP response sanitization         ✅
v0.8    GKE generator (Standard + Autopilot, private, WIF)   ✅
v0.8.1  Plugin-owned generated-file security policy          ✅
v0.9    Dependency Graph Engine                               ✅
v0.9.1  Cloud SQL generator                                   ✅
—       Secret Manager generator                              ✅
—       Artifact Registry generator (11th standalone generator) ✅
—       Multi-service architecture assembler                  ✅ (composes Network + Cloud SQL + Secret Manager + Cloud Run)
—       Full live Apply/Destroy verification, all 11 generators ✅
—       NL→Terraform intent detection extended to all 3 composed recipes ✅
—       Drift Detection (read-only, no auto-remediation)       ✅
—       Policy as Code (labels, region allowlist, naming)      ✅
—       Lightweight Module Registry (with live_verified status) ✅
—       Async Terraform SDK (AsyncTerraformClient, concurrent runs) ✅
—       Bounded Cost Optimization estimator (provisioned resources only) ✅
—       Terraform MCP Server (v2.0, scoped down — server, not client) ✅
```

## Composed architectures

Beyond the 11 standalone generators, the assembler composes multiple
generators into pre-built architectures:

| Architecture | Generators composed | Status |
|---|---|---|
| Private Cloud Run + Cloud SQL platform | Network, Cloud SQL, Secret Manager, Cloud Run | **Fully live-verified** — real network/PSA/Cloud SQL/Cloud Run all deployed, cross-module wiring confirmed (Cloud Run genuinely reached healthy/serving state), clean teardown. Confirmed 1101.5s (~18m22s). |
| BigQuery + Pub/Sub + Cloud Functions event pipeline | Pub/Sub, Cloud Functions, BigQuery | **Fully live-verified**, including a real functional test — a real Pub/Sub message was published, genuinely triggered the Cloud Function via Eventarc, and produced a real row in BigQuery. Confirmed 245.6s. |
| GKE + Network + IAM (Workload Identity) platform | GKE, IAM | **Fully live-verified** — real private GKE cluster, node pool, and a genuinely distinct Workload Identity-bound application service account (confirmed via state, not just resource existence: correct `roles/iam.workloadIdentityUser` binding scoped to the exact Kubernetes ServiceAccount). Confirmed 1216.3s (~20m16s), first try after one setup fix. |

**All three recipes are now also reachable via natural language** through
`design_infrastructure_platform` — previously only the Cloud Run + Cloud SQL
recipe was detected from request text; the other two required calling the
assembler directly. Fixed this session (see "Real bugs found" above).

**Real bugs found and fixed building the GKE platform live test:**
- `gke_deletion_protection` was entirely missing from the assembler (hardcoded `true`, no override), the same class of gap as Cloud SQL/Cloud Run — fixed properly as a real parameter, not just patched for the test.
- The assembler passes `region` straight through as the GKE module's `location`, making the cluster regional (spanning every zone at once) — reapplied the same zone-pinning fix (`us-central1-a`) the standalone GKE live test needed after a real `GCE_STOCKOUT`, plus the same `pd-standard` disk override (the generator's default `pd-balanced` had drawn on exhausted SSD quota before).
- A subtler near-miss, caught before running anything real: the first draft of that disk-type override specified only `node_config { disk_type = "pd-standard" }`. Terraform override files replace nested blocks wholesale rather than merging individual attributes — that draft would have silently dropped `service_account`, `oauth_scopes`, and `shielded_instance_config`, breaking the entire Workload Identity chain. Fixed by reproducing the full block with only `disk_type` changed.
- One simple but completely blocking naming mistake: the override file was named `live_test_overrides.tf` (plural). Terraform's override auto-detection only matches the exact suffix `_override.tf` (singular) — the plural version was silently treated as an ordinary file, producing real duplicate-resource errors instead of the intended merge. One-character-class fix, caught immediately from the error message.

**Real bugs found and fixed building the Cloud Run + Cloud SQL live test:**
- The assembler never overrode `deletion_protection` for either Cloud SQL or Cloud Run — both default `true` (the safe choice), which silently blocked `terraform destroy`. Fixed by properly exposing `db_deletion_protection` and `cloud_run_deletion_protection` as real assembler parameters, matching the pattern already used for BigQuery.
- Cloud Run's `DB_PASSWORD` env var references Secret Manager version `"latest"`, but this architecture deliberately generates no secret version at all (by design — no real credential should ever be baked into Terraform state). Fixed at the test level only: a placeholder secret version + a two-phase apply (secret first, then everything else), since the shared architecture is correct to leave real credential population out-of-band.
- A real, persistent GCP-side quirk: this project's Private Service Access peering connections took far longer than Terraform's own wait period to release during teardown — confirmed repeatedly (7+ separate attempts) even well after the last real consumer (Cloud SQL) was already gone. Fixed the correct way, using Terraform's native `deletion_policy = "ABANDON"` on just that one resource, scoped to the test only (a real production teardown should still actually delete it).
- Along the way, this quirk also caused real quota exhaustion (GCP's default 5-networks-per-project limit) from accumulated orphaned test networks, requiring manual `gcloud` cleanup a few times before the fix landed.

**Real bugs found and fixed building the event pipeline:**
- Extended the Cloud Functions generator itself with a proper `trigger_type` (HTTP/PUBSUB) option — a genuine new capability, fully backward-compatible, including the full IAM chain a Pub/Sub-triggered function needs (`roles/eventarc.eventReceiver`, `roles/run.invoker`, and the easy-to-miss Pub/Sub service-agent `roles/iam.serviceAccountTokenCreator` grant).
- The pipeline assembler initially forgot to override `deletion_protection` for the BigQuery table, blocking destroy — fixed by properly exposing it as a root-level variable (defaults `true` for real deployments, overridable for tests).
- The live test's functional verification originally shelled out to the `gcloud` and `bq` CLIs, both of which are `.cmd` wrappers on Windows that Python's `subprocess.run` can't resolve without `shell=True` — replaced with the native `google-cloud-bigquery` and `google-cloud-pubsub` Python clients, which also sidesteps an unrelated, pre-existing `bq` CLI installation bug on this machine.

## Governance and platform tools (built this session, all wired into the agent)

| Tool | What it does | Real limits, stated plainly |
|---|---|---|
| **Drift Detection** (`detect_infrastructure_drift`) | Runs `terraform plan -refresh-only` against a real workspace + real GCP credentials; reports what changed outside Terraform | Read-only by design — detection only, no auto-remediation |
| **Policy as Code** (`check_policy_compliance`) | Checks a workspace's tfvars for required labels, region allowlist membership, and naming convention | Three checks only, fully offline — not a full OPA/Sentinel-style engine |
| **Module Registry** (`list_available_infrastructure_modules`) | Structured inventory of all 11 generators + 3 composed architectures, each with a real `live_verified` field | `live_verified` reflects actual testing history, tracked explicitly — not inferred from code |
| **Async Terraform SDK** (`terraform_agent/sdk/AsyncTerraformClient`) | Purely additive async client; `run_many()`/`validate_many()` run Terraform commands concurrently across multiple workspaces | Does not replace the existing synchronous tools anywhere — zero regression risk by construction |
| **Cost Optimization** (`estimate_workspace_cost`) | Rough monthly cost estimate for provisioned (always-on) resources — Cloud SQL, GKE node pools + control-plane fee | Uses a static table of published GCP list prices (us-central1, verified 2026-07-23), not the real Billing API. Explicitly does **not** estimate usage-based services (Cloud Run, Cloud Functions, Pub/Sub, BigQuery, GCS, Artifact Registry) |
| **Terraform MCP Server** (`terraform_agent/mcp_server/`, `run_mcp_server.py`) | Exposes 21 tools over the Model Context Protocol so any MCP client (Claude Desktop, Claude Code) can use them directly | Deliberately excludes `terraform_apply`/`terraform_plan` against real state and any state read/write — real deployment stays in the more supervised ADK chat-loop path. **Live-verified working end-to-end via Claude Code**, not just unit tested |

## What's next

There is no queued "immediate next step." Every item previously listed as
"kept, scoped down to realistic solo-project size" is now done:

```
[x] Terraform Agent SDK        — done (AsyncTerraformClient)
[x] Documentation Generator    — checked; found already solid across all
                                  11 generators, minor header consistency
                                  fix applied rather than a bigger rebuild
[x] Lightweight Policy as Code — done
[x] Drift Detection (detection only) — done
[x] Lightweight Module Registry — done
[x] Check whether NL → Terraform is already covered — checked; found a
                                  real gap (only 1 of 3 recipes was
                                  detected), fixed properly
```

Two items originally marked "cut entirely" as too large for a solo
project were revisited, scoped down further than the original ask, and
built anyway:

```
[x] v2.0 Terraform MCP Server — scoped to generation/validation/
                                 governance tools only, no deployment
                                 actions exposed; live-verified via
                                 Claude Code
[x] v2.6 Cost Optimization     — scoped to provisioned, always-on
                                 resources only, static pricing table
                                 instead of live Billing API, honest
                                 about what it can't estimate
```

Genuinely still out of scope on purpose (revisit only if the project's
scale changes substantially):
- Phase 3 (Multi-Agent System, RAG Knowledge Base, Self-Healing
  Infrastructure, Platform Dashboard)
- Phase 4 (Complete Enterprise IaC Platform)
- Auto-remediation half of drift detection (detection is kept; automated
  fixing is a materially bigger safety/governance undertaking)
- Full Billing API integration, rightsizing, and FinOps forecasting for
  cost estimation

If you want a next step anyway, the two most natural extensions of
things that already exist are: adding a fourth composed architecture, or
broadening the cost estimator's static pricing table to more machine
types and services.

## Housekeeping

Confirmed done this session:
- `terraform_agent/tools/system_prompt.py` (an abandoned early draft of
  the system prompt, never imported by anything — the real one lives at
  `terraform_agent/prompts/system_prompt.py`) — removed
- `pubsub-e2e-input.txt` (a one-off manual test input, unreferenced) —
  removed
- `requirements.txt`'s `pytestmcp` line (two concatenated package names,
  `pytest` + `mcp`, that had never resolved to a real package) — fixed
- The four `test/*-e2e-automation` branches, all fully merged into
  `main` — deleted, both locally and on `origin`

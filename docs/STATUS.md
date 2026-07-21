# terraform-adk-agent — Status

_This is the canonical, up-to-date status doc for this project. Update this
file directly when things change — don't keep a separate copy elsewhere,
since that's exactly how the previous version of this table went stale._

Last verified: 2026-07-21

## Test Report

| Generator       | Generate | Validate | Plan | Apply | Destroy | Status |
|-----------------|:--------:|:--------:|:----:|:-----:|:-------:|--------|
| GCS             | ✅       | ✅       | ✅   | ✅    | ✅      | Completed |
| Secret Manager  | ✅       | ✅       | ✅   | ✅    | ✅      | Completed |
| IAM             | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 75s |
| Pub/Sub         | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 79s |
| BigQuery        | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 38s |
| Network (VPC)   | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 533s |
| Cloud Functions | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 141s (2 real bugs fixed) |
| Cloud Run       | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 73s |
| Cloud SQL       | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 618s (1 real bug fixed) |
| GKE             | ✅       | ✅       | ✅   | ✅    | ✅      | Completed — live confirmed 917s (2 real bugs + 3 environment issues fixed) |

**All 10 generators: fully complete.** Generate/Validate verified by unit
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

## Roadmap — reconciled with what's actually shipped

The original version-numbered roadmap (v0.6 → v2.0, ending at "Terraform
MCP Server") undersold real progress. Confirmed shipped, per
`docs/migration/*.md` and this cycle's live-testing work:

```
v0.5    Plugin-based Multi-Service Generator Framework      ✅
v0.6    Cloud Run generator                                 ✅
v0.7    HashiCorp Terraform MCP Server integration           ✅ (already shipped — not a v2.0 item)
v0.7.2  Terraform Registry MCP response sanitization         ✅
v0.8    GKE generator (Standard + Autopilot, private, WIF)   ✅
v0.8.1  Plugin-owned generated-file security policy          ✅
v0.9    Dependency Graph Engine                               ✅
v0.9.1  Cloud SQL generator                                   ✅
—       Secret Manager generator                              ✅
—       Multi-service architecture assembler                  ✅ (composes Network + Cloud SQL + Secret Manager + Cloud Run)
—       Full live Apply/Destroy verification, all 10 generators ✅ (this cycle)
```

## Composed architectures

Beyond the 10 standalone generators, the assembler composes multiple
generators into pre-built architectures:

| Architecture | Generators composed | Status |
|---|---|---|
| Private Cloud Run + Cloud SQL platform | Network, Cloud SQL, Secret Manager, Cloud Run | Plan-level validated; not yet live-tested as a combined stack |
| BigQuery + Pub/Sub + Cloud Functions event pipeline | Pub/Sub, Cloud Functions, BigQuery | **Fully live-verified**, including a real functional test — a real Pub/Sub message was published, genuinely triggered the Cloud Function via Eventarc, and produced a real row in BigQuery. Confirmed 245.6s. |

**Real bugs found and fixed building the event pipeline:**
- Extended the Cloud Functions generator itself with a proper `trigger_type` (HTTP/PUBSUB) option — a genuine new capability, fully backward-compatible, including the full IAM chain a Pub/Sub-triggered function needs (`roles/eventarc.eventReceiver`, `roles/run.invoker`, and the easy-to-miss Pub/Sub service-agent `roles/iam.serviceAccountTokenCreator` grant).
- The pipeline assembler initially forgot to override `deletion_protection` for the BigQuery table, blocking destroy — fixed by properly exposing it as a root-level variable (defaults `true` for real deployments, overridable for tests).
- The live test's functional verification originally shelled out to the `gcloud` and `bq` CLIs, both of which are `.cmd` wrappers on Windows that Python's `subprocess.run` can't resolve without `shell=True` — replaced with the native `google-cloud-bigquery` and `google-cloud-pubsub` Python clients, which also sidesteps an unrelated, pre-existing `bq` CLI installation bug on this machine.

## What's next

The trimmed roadmap items below are still open. The "Cloud Run + Cloud SQL"
architecture is a reasonable candidate for the same live-testing treatment
the event pipeline just received, if there's appetite for it.


The original v2.0-v4.0 vision included several items scoped for a
multi-year commercial platform team, not a solo project. Cut those
entirely rather than let them go stale on paper again. What's left is
realistic, buildable incrementally, and mostly extends things that
already exist.

**Cut entirely** (kept out of scope on purpose — revisit only if the
project's scale genuinely changes):
- Phase 3 (Multi-Agent System, RAG Knowledge Base, Self-Healing
  Infrastructure, Platform Dashboard)
- Phase 4 (Complete Enterprise IaC Platform)
- v2.0 Enterprise MCP Server as a second, bigger MCP layer (basic
  Terraform MCP integration already shipped at v0.7)
- v2.6 Cost Optimization Engine (full Billing API + forecasting scope)
- Auto-remediation half of drift detection (detection is kept, see below)

**Immediate next step:**
```
[ ] Expand the multi-service architecture assembler
    - GKE + Network + IAM (private, VPC-native Kubernetes platform stack), or
    - BigQuery + Pub/Sub + Cloud Functions (event-driven data pipeline)
    - Give the composed stack the same live E2E treatment each
      standalone generator already received
```

**Kept, scoped down to realistic solo-project size, roughly in order:**
```
[ ] Terraform Agent SDK       — refactor existing CLI-wrapping code
                                 (terraform_runner.py, tools/) into a
                                 clean, reusable async SDK layer
[ ] Documentation Generator   — extend the README-per-module pattern
                                 several generators already have,
                                 consistently across all 10
[ ] Lightweight Policy as Code — simple Python checks (required labels,
                                 naming, region allowlist) run before
                                 generate/apply; not a full OPA-style engine
[ ] Drift Detection (detection only) — compare live state vs. real GCP,
                                 report differences; no auto-remediation
[ ] Lightweight Module Registry — static manifest of the 10 modules with
                                 metadata; no separate search/dependency-
                                 graph systems
[ ] Check whether the AI Assistant idea (NL → Terraform) is already
    covered by the existing ADK agent before building anything new
```

Nothing here is version-numbered on purpose — these are independent,
pick-what-you-need items now, not a strict sequence.

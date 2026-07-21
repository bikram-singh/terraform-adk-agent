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

## What's actually next

Every standalone generator is fully proven — plan-level and live
apply/destroy alike. The honest next milestone is **composing generators
together** into more pre-built architectures, the same way
`assembler_tools.py` already composes Network + Cloud SQL + Secret
Manager + Cloud Run:

```
[ ] GKE + Network + IAM              — private, VPC-native Kubernetes platform stack
[ ] BigQuery + Pub/Sub + Cloud Functions — event-driven data pipeline
[ ] Give the existing Cloud Run + Cloud SQL + Secret Manager assembler its own live E2E test
    (its pieces are proven individually, but never tested live as a combined stack)
```

Pick whichever matches a real use case first; these aren't sequenced by
version number the way the original roadmap was, since they're
independent compositions of already-proven parts.

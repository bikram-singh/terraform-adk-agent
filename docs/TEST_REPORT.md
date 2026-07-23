# Terraform ADK Agent — Test Report

_This file reports the unit test suite's current pass/fail state only.
Per-generator Generate/Validate/Plan/Apply/Destroy status, composed
architecture status, and the governance/platform tools table all live in
`docs/STATUS.md` — the canonical status doc. Keeping a second,
hand-maintained copy of that same table here is exactly what let this file
go stale relative to STATUS.md before; don't reintroduce that duplication._

Last verified: 2026-07-23

## Latest full run

```
227 passed, 1 skipped, 0 real failures
```

```powershell
pytest tests/unit -q
```

## Known, non-code environmental limitations

A handful of tests only pass with a real `terraform` binary on `PATH` and
valid GCP credentials (e.g. `test_architect_designs_and_assembles_full_platform`,
`test_assembler_composes_and_validates_full_architecture`,
`test_assembler_truncates_long_vpc_connector_name`). In an environment
without both of those, these fail with `Terraform executable was not
found` or a real GCP auth error — not because anything in the generated
Terraform is wrong. Confirmed clean on this machine, which has both.

## Live E2E tests (opt-in, real GCP — not part of the default `pytest` run)

These require `TERRAFORM_E2E_LIVE=true` and `TERRAFORM_ALLOW_APPLY=true`,
plus a real project ID env var per test (see each test file's fixtures).
Skipped by default; see `docs/STATUS.md` for each one's live-verification
status and timing.

```
tests/e2e/test_gcs_live_e2e.py
tests/e2e/test_cloudrun_live_e2e.py
tests/e2e/test_cloudsql_live_e2e.py
tests/e2e/test_pubsub_live_e2e.py
tests/e2e/test_bigquery_live_e2e.py
tests/e2e/test_cloud_functions_live_e2e.py
tests/e2e/test_secret_manager_live_e2e.py
tests/e2e/test_iam_live_e2e.py
tests/e2e/test_network_live_e2e.py
tests/e2e/test_gke_live_e2e.py
tests/e2e/test_artifact_registry_live_e2e.py
tests/e2e/test_cloudrun_cloudsql_live_e2e.py       # composed architecture
tests/e2e/test_event_driven_pipeline_live_e2e.py   # composed architecture
tests/e2e/test_gke_platform_live_e2e.py            # composed architecture
```

If a filename above doesn't match what's actually in `tests/e2e/` on a
given checkout, trust the filesystem over this list and update this list
to match — this is a pointer, not a second source of truth.

## Housekeeping

The four `test/*-e2e-automation` branches (`cloudrun`, `cloudsql`, `gcs`,
`pubsub`) were confirmed fully merged into `main` and deleted, both
locally and on `origin`, this session. `git branch` / `git ls-remote
--heads origin` should show only `main`.

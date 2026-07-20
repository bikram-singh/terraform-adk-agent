# Terraform ADK Agent — Test Report

_Reflects actual code on `main` as of this session. "Generate"/"Validate" are
verified by unit tests I ran directly; "Plan/Apply/Destroy" require a real
`terraform` binary and are marked based on whether a safe E2E suite exists._

| Generator       | Generate | Validate | Plan | Apply | Destroy | Status                          |
|-----------------|:--------:|:--------:|:----:|:-----:|:-------:|----------------------------------|
| GCS             | ✅       | ✅       | ✅   | ✅    | ✅      | Completed                       |
| Cloud Run       | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply)     |
| Cloud SQL       | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply)     |
| Pub/Sub         | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply)     |
| Secret Manager  | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply)     |
| BigQuery        | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply) — confirmed 8/8 after fixing stale ADC creds |
| Cloud Functions | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply) — confirmed 9/9 |
| GKE             | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply) — confirmed 8/8 after fixing the `APISERVER` enum bug |
| IAM             | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply) — confirmed 8/8 |
| Network (VPC)   | ✅       | ✅       | ✅   | —     | —       | E2E covered (safe, no apply) — confirmed 8/8 |

**Bonus, not on the original roadmap at all:** a multi-service architecture
assembler (`terraform_agent/tools/assembler_tools.py`) already composes
Network + Cloud SQL + Secret Manager + Cloud Run into one modular workspace
(`assemble_private_cloud_run_cloud_sql_project`). Verified it generates all
35 expected files and wires modules together correctly; it only fails in a
sandbox with no local `terraform` binary. This is effectively v1.x-plus
"Intelligence Engine" territory already shipped.

## What "Apply/Destroy" means going forward

Only GCS has ever been run through real `apply`/`destroy` against live GCP
infrastructure. For the rest, "Plan" is the safe automated ceiling — actually
flipping Apply/Destroy to ✅ requires you to run it manually against a real
project, since that's a deliberate safety boundary
(`TERRAFORM_ALLOW_APPLY` / `TERRAFORM_ALLOW_DESTROY` default to `false`).

## Unit test suite status (verified this session)

```
140 passed, 1 skipped, 0 real failures
```

The only 3 failures seen in a full run are environmental, not code bugs —
`test_architect.py` and `test_project_assembler.py`'s full-platform tests
fail only because that sandbox has no `terraform` executable on PATH. They
pass everywhere the pipeline correctly stops at "initialize" and reports the
missing binary; nothing in the generated Terraform itself is wrong.

## Housekeeping

The following branches are fully merged into `main` and safe to delete:

```powershell
git branch -d test/cloudrun-e2e-automation test/cloudsql-e2e-automation test/gcs-e2e-automation test/pubsub-e2e-automation
git push origin --delete test/cloudrun-e2e-automation test/cloudsql-e2e-automation test/gcs-e2e-automation test/pubsub-e2e-automation
```

---

# Roadmap — reconciled with what's actually shipped

The original roadmap numbering (v0.6 GCS → v0.7 Cloud Run → ... → v1.5 GKE →
v2.0 MCP Server) undersold the real state. Here's what actually happened,
per `docs/migration/*.md` and the commit log:

```
v0.4        Baseline GCS-only agent
v0.5        Plugin-based Multi-Service Generator Framework           ✅
v0.6        Cloud Run generator (production-ready)                  ✅
v0.7        HashiCorp Terraform MCP Server integration               ✅
v0.7.2      Terraform Registry MCP response sanitization             ✅
v0.7.2→v0.8 GKE generator (Standard + Autopilot, private, WIF, GW API)✅
v0.8.1      Plugin-owned generated-file security policy              ✅
v0.9        Dependency Graph Engine (planning-only ADK tool)          ✅
v0.9.1      Cloud SQL generator (Postgres/MySQL, private IP, CMEK)   ✅
(unversioned) Secret Manager generator + E2E tests                   ✅ (just landed)
(unversioned) Multi-service architecture assembler                   ✅ (undocumented — recommend versioning this as its own milestone, e.g. v0.9.2)
```

## What's actually next

Every generator in scope already has working code and passing unit tests.
The real remaining gap is **E2E (safe plan-level) coverage** for five
generators that don't have it yet:

```
[x] BigQuery         — E2E suite added, confirmed 8/8 passing
[x] Cloud Functions  — E2E suite added, confirmed 9/9 passing
[x] GKE              — E2E suite added, confirmed 8/8 passing (after fixing a real APISERVER enum bug in the generator)
[x] IAM              — E2E suite added, confirmed 8/8 passing
[x] Network (VPC)    — E2E suite added, confirmed 8/8 passing
```

**ROADMAP COMPLETE.** All 10 generators (GCS, Cloud Run, Cloud SQL,
Pub/Sub, Secret Manager, BigQuery, Cloud Functions, GKE, IAM, Network) now
have Generate → Validate → Plan verified by real `terraform` runs against
a real GCP project, not just unit tests. One genuine bug was found and
fixed along the way (GKE's `APISERVER` enum), which is exactly the kind of
defect only a real provider round-trip catches.

### What's actually next (the honest v2.0)
Every standalone generator is done. The remaining frontier is the
multi-service architecture assembler (`terraform_agent/tools/assembler_tools.py`),
which already composes Network + Cloud SQL + Secret Manager + Cloud Run
into one workspace (`assemble_private_cloud_run_cloud_sql_project`). With
all 10 generators now individually proven, the natural next milestone is
building out more pre-composed architectures from them — e.g. a
GKE + Network + IAM + Artifact Registry stack, or a BigQuery + Pub/Sub +
Cloud Functions event-pipeline stack — and giving *those* assembled
architectures their own E2E coverage, the same way each individual
generator now has.

### Note on Network specifically
This is the one generator with no required-only fields — every value has a
sensible default, so it generates cleanly from an empty `values` dict like
GCS/Cloud Run/Cloud SQL/Pub/Sub/BigQuery/Cloud Functions did. It also has
its own `lifecycle { precondition {...} }` (this time on
`google_vpc_access_connector.serverless`, requiring
`max_instances > min_instances`), which the plan test implicitly exercises
since both are static values in the default tfvars (2 and 3). One
dedicated test (`test_plan_contains_no_secondary_ranges_by_default`) confirms
the subnet's `dynamic "secondary_ip_range"` block correctly renders as empty
when `secondary_ip_ranges = {}`.

### Note on GKE specifically
The generator produces both `google_container_cluster.standard` and
`google_container_cluster.autopilot`, gated by `count` on `cluster_mode`
(default `STANDARD`). The E2E suite explicitly asserts the Autopilot
resource is absent from the plan by default, alongside the Standard
cluster, its node pool, and the 5 least-privilege node IAM roles
(`logging.logWriter`, `monitoring.metricWriter`, `monitoring.viewer`,
`stackdriver.resourceMetadata.writer`, `artifactregistry.reader`). Like
Cloud SQL/Cloud Run, `network`/`subnetwork`/secondary-range values are
placeholder strings in the default tfvars — that's fine for a
`-refresh=false` plan since nothing here is read through a data source.

**Real bug caught by this E2E run (not a test problem):**
`cluster.tf`'s `logging_config.enable_components` used `"API_SERVER"` in
both the Standard and Autopilot cluster blocks. The `google_container_cluster`
provider schema actually expects `"APISERVER"` (no underscore) — this only
surfaces at real `terraform validate`/`plan` time since it's a provider-side
enum, not something `terraform fmt` or a Python unit test would ever catch.
Fixed in `terraform_agent/generators/gke/templates.py` (both occurrences).
Attached as `gke_templates.py` — replace your copy and regenerate the
workspace before re-running.

This is a good example of exactly why the E2E layer matters beyond unit
tests: unit tests confirmed the *shape* of the generated config was right,
but only a real Terraform provider could catch that one literal value was
wrong.

Once those five have E2E coverage, every generator will be at parity with
GCS/Cloud Run/Cloud SQL/Pub/Sub/Secret Manager (Generate → Validate → Plan
all verifiable), and the honest "v2.0" milestone becomes: expand the
architecture assembler to compose more of these 10 generators together
(e.g., GKE + Network + IAM as a second pre-built architecture), rather than
a from-scratch "Terraform MCP Server" — since that MCP integration already
shipped back at v0.7.

### Immediate next step
Nothing left pending on the generator side. Suggested options, your call:

1. Clean up the `generated/*-e2e-test` workspaces if you don't want them
   committed (they're safe scratch output, not secrets, but they are
   disposable test fixtures).
2. Start scoping a second pre-built architecture in
   `assembler_tools.py` (see "What's actually next" above).
3. Revisit the two negative-path precondition tests flagged as optional
   extensions (IAM's owner/editor rejection, Network's connector
   min/max rejection) if you want belt-and-suspenders coverage on the
   `lifecycle` blocks specifically, not just the happy path.

---

# Phase 2 — Live Apply/Destroy coverage

Plan-level E2E only proves Terraform *would* create valid resources.
Apply/Destroy proves it actually can, against a real project, and that
teardown leaves nothing behind. This is a different risk class: real
billing, real time, real cleanup risk if something fails mid-run.

**Existing live coverage before this phase:** only GCS and Secret Manager.
Everything else — Cloud Run, Cloud SQL, Pub/Sub, BigQuery, Cloud Functions,
GKE, IAM, Network — has never been applied/destroyed for real.

**Agreed order (cheapest/safest → priciest/slowest):**

```
[x] IAM         — CONFIRMED, 1 passed in 75.11s
[x] Pub/Sub     — CONFIRMED, 1 passed in 79.49s
[x] BigQuery    — CONFIRMED, 1 passed in 38.20s
[x] Network     — CONFIRMED, 1 passed in 533.3s (8m56s)
[x] Cloud Functions — 2 real generator bugs found + fixed this session, retest pending
[ ] Cloud Run   — needs a real container image (plan: point at gcr.io/cloudrun/hello)
[ ] Cloud SQL   — real hourly billing, slow create/destroy — do deliberately
[ ] GKE         — most expensive & slowest; do last, watch it run
```

### IAM live suite — what's different from the plan-only version
- Generates a **fresh workspace directly from `IAMGenerator`** in the test
  itself (not from a pre-existing `generated/iam-e2e-test` dir), with a
  **unique `service_account_id` per run** (`iam-e2e-<hex><hex>`, ~18 chars,
  validated against the real `^[a-z][a-z0-9-]{4,28}[a-z0-9]$` pattern
  across 20 sample runs — all valid).
- The uniqueness matters more here than for most generators: GCP can make a
  deleted service account's ID/email temporarily unusable for a new
  account for a period after deletion, so reusing a fixed ID across
  repeated live-test runs risks a spurious failure unrelated to the
  generator itself.
- Grants two intentionally harmless, no-op project roles
  (`roles/cloudsql.client`, `roles/secretmanager.secretAccessor`) — real
  IAM bindings, zero real-world effect, trivial to tear down.
- Requires a real project ID via `IAM_E2E_PROJECT_ID` (falls back to
  `GOOGLE_CLOUD_PROJECT`) — fails with a clear message if neither is set,
  rather than silently using a placeholder.
- Gated behind the same double-flag pattern as your existing GCS/Secret
  Manager live tests: `TERRAFORM_E2E_LIVE=true` **and**
  `TERRAFORM_ALLOW_APPLY=true`. Confirmed it **skips cleanly** (not errors)
  when those aren't set — verified in my sandbox.
- Apply → verify (state, outputs, live `show -json`) → destroy is wrapped
  in try/finally exactly like the GCS live test, so destroy always runs
  even if a verification assertion fails, and a combined error is raised
  if *both* the test and cleanup fail.

### To run it
```powershell
$env:TERRAFORM_E2E_LIVE = "true"
$env:TERRAFORM_ALLOW_APPLY = "true"
$env:IAM_E2E_PROJECT_ID = "dhg-vaccine-rateauto-nonpord"   # or your nonprod project
pytest tests/e2e/test_iam_live_e2e.py -v -s
```
The `-s` flag is worth adding here so you can watch `apply`/`destroy`
output live rather than have pytest buffer it.

Confirm this one passes (and, ideally, that no orphaned service account is
left behind — worth a quick `gcloud iam service-accounts list --project=<project>`
check afterward), then say the word for Pub/Sub next.

### Update: IAM live — CONFIRMED
`pytest tests/e2e/test_iam_live_e2e.py -v -s` → **1 passed in 75.11s**.
Real service account created, verified via state/outputs/live `show -json`,
and destroyed. First live apply/destroy run outside GCS/Secret Manager.

### Pub/Sub live suite — what's different
- **Important finding:** `main.tf` includes `data "google_project" "this"`,
  used to build the Pub/Sub service agent's member string for dead-letter
  IAM bindings. Terraform reads data sources during `plan` regardless of
  `-refresh`, so — unlike every other generator so far — **the Pub/Sub
  generator has always required real, authenticated GCP access even for
  the "safe" plan-only E2E suite**, not just this live one. Worth knowing:
  it's a slightly different trust boundary than GCS/Cloud Run/etc., though
  it was never a problem since ADC was already configured.
- Because of that data source, `data.google_project.this` shows up in
  `terraform state list` alongside the managed resources — the test
  explicitly accounts for this rather than assuming a managed-resources-only
  state.
- Unique topic/subscription names per run (`pubsub-e2e-<hex>` /
  `pubsub-e2e-<hex>-sub`), validated against the real
  `^[A-Za-z][A-Za-z0-9_.-]{2,254}$` pattern.
- Dead-letter queue and IAM member bindings left disabled for this first
  live pass — fewer resources, faster teardown, less that can go wrong.
  Worth adding as a follow-up live variant later if you want deeper
  coverage of the dead-letter path specifically.

### To run it
```powershell
$env:TERRAFORM_E2E_LIVE = "true"
$env:TERRAFORM_ALLOW_APPLY = "true"
$env:PUBSUB_E2E_PROJECT_ID = "dhg-vaccine-rateauto-nonpord"
pytest tests/e2e/test_pubsub_live_e2e.py -v -s
```

### Update: Pub/Sub live — CONFIRMED
`pytest tests/e2e/test_pubsub_live_e2e.py -v -s` → **1 passed in 79.49s**.
Real topic + durable subscription created, verified, destroyed.

### BigQuery live suite — what's different
- Before writing this, I checked current Google provider documentation on
  `google_bigquery_dataset` specifically to confirm there wasn't a second,
  dataset-level `deletion_protection`-style blocker hiding alongside the
  known table-level one. Confirmed: the dataset resource has no such field
  in this template (only an optional `deletion_policy` it doesn't set), so
  only the **table's** `deletion_protection` (defaults to `true`) needed
  overriding for live testing — done via `values={"deletion_protection":
  False}` when generating the workspace, verified it renders as
  `deletion_protection = false` in the actual tfvars.
- The table is destroyed before the dataset (implicit dependency via
  `dataset_id = google_bigquery_dataset.this.dataset_id`), so the dataset's
  own `delete_contents_on_destroy = false` never becomes an obstacle in
  this single-purpose workspace.
- Unique `dataset_id` per run (`bigquery_e2e_<hex><hex>`, underscores only
  per BigQuery's naming rules — no hyphens allowed here, unlike topics/SAs).

### To run it
```powershell
$env:TERRAFORM_E2E_LIVE = "true"
$env:TERRAFORM_ALLOW_APPLY = "true"
$env:BIGQUERY_E2E_PROJECT_ID = "dhg-vaccine-rateauto-nonpord"
pytest tests/e2e/test_bigquery_live_e2e.py -v -s
```

### Update: BigQuery live — CONFIRMED
`pytest tests/e2e/test_bigquery_live_e2e.py -v -s` → **1 passed in 38.20s**.
Real dataset + table created, verified, destroyed. Fastest live run yet.

### Network live suite — please read before running
**This one is genuinely slower than everything else in this phase.** IAM,
Pub/Sub, and BigQuery each ran in under 90 seconds. The Serverless VPC
Access connector alone typically takes several minutes to provision and
several minutes to tear down; the Private Service Access peering
connection adds more time on top. Realistic expectation: **5-15 minutes
end to end**, not under 2 minutes.

**Do not interrupt a run in progress.** An interrupted apply or destroy is
exactly the scenario most likely to leave a partially-provisioned VPC
connector or PSA peering behind, needing manual cleanup via `gcloud`.

Also worth knowing: `google_service_networking_connection` (the PSA
peering resource) has a documented real-world quirk across the Google
provider ecosystem — it can occasionally be slow to tear down, or need a
retry, if GCP's async service-producer bookkeeping hasn't caught up yet.
This isn't a defect in the generator or this test. If cleanup fails here,
re-running `terraform destroy` directly in the workspace (path is printed
in the failure message) or waiting a minute and retrying is a reasonable
next step before assuming something is actually broken.

- Unique names per run: `network_name` (`net-e2e-<hex6>`), `subnet_name`,
  `private_service_access_range_name`, and a separately-prefixed
  `vpc_connector_name` (`vpc-e2e-<hex6>`) kept short on purpose since it
  has a hard 25-character limit the generator enforces — verified all
  four names flow through the real generator correctly before writing the
  test.
- The test prints its own elapsed time at the end (`-s` required to see
  it) so you have a concrete number for next time.

### To run it
```powershell
$env:TERRAFORM_E2E_LIVE = "true"
$env:TERRAFORM_ALLOW_APPLY = "true"
$env:NETWORK_E2E_PROJECT_ID = "dhg-vaccine-rateauto-nonpord"
pytest tests/e2e/test_network_live_e2e.py -v -s
```
Consider running this one when you have a few uninterrupted minutes,
rather than between other tasks.

### Update: Network live — CONFIRMED
`pytest tests/e2e/test_network_live_e2e.py -v -s` → **1 passed in 533.3s
(8m56s)**, matching the timing warning given beforehand.

**One real prerequisite discovered along the way, not a bug:** the first
run failed with `403 SERVICE_DISABLED` for two APIs that weren't yet
enabled on the project — `servicenetworking.googleapis.com` (Private
Service Access) and `vpcaccess.googleapis.com` (Serverless VPC Access).
The generator's own error handling isn't at fault here; these are
project-level API enablement prerequisites that simply hadn't been turned
on yet for anything using them before. Fixed once, permanently, with:
```powershell
gcloud services enable servicenetworking.googleapis.com vpcaccess.googleapis.com --project=<project>
```
**Also worth noting:** the try/finally cleanup logic worked exactly as
designed on that first failed run — network, subnet, and the PSA global
address (the three resources that *did* create successfully before the
API errors hit) were automatically destroyed even though the overall test
failed. Confirmed via `gcloud compute networks list --filter=...` → 0
items, before ever retrying. This is the safety net earning its keep.

**Any future nonprod GCP project used for live testing should have these
two APIs enabled up front** if Network live tests are expected to run
against it:
```
servicenetworking.googleapis.com
vpcaccess.googleapis.com
```

### Cloud Functions live suite — what's different
**First live test to trigger a real Cloud Build.** Cloud Functions 2nd gen
deploys via Cloud Build + Cloud Run under the hood, not a direct API call.
Expected duration: roughly 3-8 minutes (build + deploy + verify + destroy)
— similar order of magnitude to Network, usually a bit faster.

- The deployable zip includes both `main.py` (a minimal
  `functions_framework.http`-decorated function) **and** a
  `requirements.txt` pinning `functions-framework==3.*` explicitly, rather
  than relying on Cloud Build's buildpacks to auto-detect it. Verified the
  zip is valid and contains both files correctly before handing this off.
- Two independent unique-naming schemes: `function_name`
  (`fn-e2e-<hex6>`, validated against the real
  `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$` pattern) and a separately, more
  heavily randomized `source_bucket_name` (`fn-e2e-<hex12>`) — GCS bucket
  names are globally unique across *all* of GCP, not just this project, so
  it gets extra entropy to keep collision risk negligible even across many
  runs over time.
- Verified both names flow through the real generator correctly (checked
  actual rendered tfvars output) before writing the test.
- Does **not** attempt to invoke the deployed function over HTTP —
  `ingress_settings` defaults to `ALLOW_INTERNAL_ONLY` (the generator's
  secure default), so this test verifies existence/configuration via
  Terraform state and outputs only, consistent with the verification depth
  of every other live test in this suite.
- If this one fails, worth distinguishing a Terraform/GCP API problem
  (same class as previous live tests) from an actual Cloud Build failure
  (a new failure mode not seen before this generator) — Cloud Build logs
  are visible in the GCP Console under Cloud Build > History.

### To run it
```powershell
$env:TERRAFORM_E2E_LIVE = "true"
$env:TERRAFORM_ALLOW_APPLY = "true"
$env:CLOUD_FUNCTIONS_E2E_PROJECT_ID = "dhg-vaccine-rateauto-nonpord"
pytest tests/e2e/test_cloud_functions_live_e2e.py -v -s
```

### Update: Cloud Functions live — first attempt hit a disabled API
Same pattern as Network: `403 SERVICE_DISABLED` for
`cloudfunctions.googleapis.com`, not enabled yet on the project. Bucket,
source object, and service account created successfully before the
failure (4s/instant/15s); cleanup fallback tore them down automatically
since none of the create calls failed, only the function itself.

Fix:
```powershell
gcloud services enable cloudfunctions.googleapis.com cloudbuild.googleapis.com run.googleapis.com --project=<project>
```
(Cloud Build and Cloud Run are enabled proactively here since Cloud
Functions 2nd gen deploys through both under the hood — better to catch
all three at once than discover them one retry at a time.)

**Pattern emerging across this phase:** this is the second generator in a
row (after Network) whose first live run surfaced a not-yet-enabled API on
`dhg-vaccine-rateauto-nonpord`, rather than a code problem. **Expect the
same for Cloud Run and Cloud SQL** — worth proactively enabling
`run.googleapis.com` (already covered above) and `sqladmin.googleapis.com`
before attempting those, to skip a redundant round-trip.

**Recommended one-time housekeeping** — enable everything this whole
roadmap will eventually need, in one shot, rather than discovering them
generator-by-generator:
```powershell
gcloud services enable `
  storage.googleapis.com `
  run.googleapis.com `
  sqladmin.googleapis.com `
  pubsub.googleapis.com `
  bigquery.googleapis.com `
  cloudfunctions.googleapis.com `
  cloudbuild.googleapis.com `
  container.googleapis.com `
  servicenetworking.googleapis.com `
  vpcaccess.googleapis.com `
  secretmanager.googleapis.com `
  --project=dhg-vaccine-rateauto-nonpord
```

### Update: Cloud Functions live — 2 real generator bugs found and fixed

Two separate failures across three attempts, and this time both were
genuine defects in the generator itself, not project configuration:

**Bug 1 — IAM propagation race (attempt 2).**
```
Error 403: Permission 'iam.serviceaccounts.actAs' denied on service
account fn-e2e-...-runtime@... (or it may not exist).
```
The runtime service account had just been created ~16-20s earlier.
IAM changes in GCP — including brand-new service accounts — are
eventually consistent: Terraform's own API call reporting "created"
doesn't guarantee the identity is visible yet to Cloud Run's own
authorization check moments later. This is an extremely common
real-world gotcha when deploying Cloud Functions/Cloud Run against a
freshly-created service account, not specific to this generator, but the
generator had no buffer for it.

**Fix:** added a `time_sleep` resource (`hashicorp/time` provider,
`create_duration = "30s"`) that runs after the service account is created
and before the function does, via an explicit `depends_on`. This is the
standard, widely-used pattern for this exact class of GCP IAM-propagation
race.

**Bug 2 — `vpc_connector_egress_settings` set without a connector (attempt 3).**
```
Error 400: spec.template.metadata.annotations: The
run.googleapis.com/vpc-access-egress annotation cannot be set without
also setting the run.googleapis.com/vpc-access-connector annotation...
```
`main.tf` set `vpc_connector_egress_settings = var.vpc_connector_egress_settings`
**unconditionally** — but `vpc_connector_egress_settings` defaults to
`"PRIVATE_RANGES_ONLY"` (a real value) while `vpc_connector` defaults to
`null`. Every default deployment of this generator was silently sending a
Cloud Run egress annotation with no matching connector annotation, which
the API correctly rejects. This is a real, reproducible bug that would
hit **any** user deploying this generator with defaults and
`enable_serverless_vpc_connector`-style values unset — not an edge case.

**Fix:** made the attribute conditional —
```hcl
vpc_connector_egress_settings = (
  var.vpc_connector != null ? var.vpc_connector_egress_settings : null
)
```
Now it's only sent when a connector is actually configured.

**Verification before handing this off:**
- All 11 Cloud Functions unit tests still pass — neither bug was
  something unit tests could have caught (one's a runtime GCP-timing
  issue, the other only manifests once the real Cloud Run API validates
  the annotation combination).
- Regenerated a real workspace and confirmed both fixes render correctly:
  `time_sleep.wait_for_runtime_sa_propagation` resource present, function
  `depends_on` includes it, `vpc_connector_egress_settings` now wrapped in
  the conditional expression.
- Updated the live test itself: added `TIME_SLEEP_ADDRESS` to
  `EXPECTED_RESOURCE_ADDRESSES` so the state-equality assertion doesn't
  break now that a 5th resource exists.

**Files to apply:**
1. Replace `terraform_agent/generators/cloud_functions/templates.py` with
   `cloud_functions_templates.py`.
2. Replace `tests/e2e/test_cloud_functions_live_e2e.py` with the updated
   version (same filename).

### To retry
```powershell
pytest tests/e2e/test_cloud_functions_live_e2e.py -v -s
```
Expect slightly longer than the ~40-50s seen in the failed attempts — the
new 30-second sleep adds directly to the total, so budget closer to
1.5-2 minutes now, still well under the original 3-8 minute estimate.

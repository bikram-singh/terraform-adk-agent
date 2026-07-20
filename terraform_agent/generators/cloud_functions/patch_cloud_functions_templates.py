"""One-time patch script for terraform_agent/generators/cloud_functions/templates.py

Run this from the repository root:

    python patch_cloud_functions_templates.py

It applies two fixes directly to the file on disk:
1. Adds the hashicorp/time provider requirement.
2. Fixes vpc_connector_egress_settings to be null when no connector is set.
3. Adds a time_sleep buffer for IAM propagation before the function is created.

Safe to run more than once -- it checks whether each fix is already present
before applying it, and reports what it did.
"""

from __future__ import annotations

from pathlib import Path

TARGET = Path("terraform_agent/generators/cloud_functions/templates.py")


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(
            f"Could not find {TARGET}. Run this script from the "
            "repository root (the folder containing terraform_agent/)."
        )

    content = TARGET.read_text(encoding="utf-8")
    original_content = content
    changes_made = []

    # Fix 1: add the hashicorp/time provider requirement.
    old_versions = (
        'terraform {\n'
        '  required_version = "$terraform_version"\n'
        '\n'
        '  required_providers {\n'
        '    google = {\n'
        '      source  = "$provider_source"\n'
        '      version = "$provider_version"\n'
        '    }\n'
        '  }\n'
        '}\n'
        '"""\n'
        '\n'
        'PROVIDERS_TEMPLATE = """\n'
        'provider "google" {\n'
        '  project = var.project_id\n'
        '  region  = var.region\n'
        '}\n'
    )
    new_versions = (
        'terraform {\n'
        '  required_version = "$terraform_version"\n'
        '\n'
        '  required_providers {\n'
        '    google = {\n'
        '      source  = "$provider_source"\n'
        '      version = "$provider_version"\n'
        '    }\n'
        '    time = {\n'
        '      source  = "hashicorp/time"\n'
        '      version = ">= 0.9.0, < 1.0.0"\n'
        '    }\n'
        '  }\n'
        '}\n'
        '"""\n'
        '\n'
        'PROVIDERS_TEMPLATE = """\n'
        'provider "google" {\n'
        '  project = var.project_id\n'
        '  region  = var.region\n'
        '}\n'
    )

    if "hashicorp/time" in content:
        print("[skip] time provider requirement already present")
    elif old_versions in content:
        content = content.replace(old_versions, new_versions, 1)
        changes_made.append("added hashicorp/time provider requirement")
    else:
        print(
            "[warn] could not find the expected VERSIONS_TEMPLATE block "
            "to patch -- it may already differ from what this script "
            "expects. Skipping this fix; check the file manually."
        )

    # Fix 2: make vpc_connector_egress_settings conditional on
    # vpc_connector actually being set, and add the time_sleep dependency
    # to the function's depends_on list.
    old_service_config_tail = (
        '    vpc_connector                   = var.vpc_connector\n'
        '    vpc_connector_egress_settings   = var.vpc_connector_egress_settings\n'
        '\n'
        '    dynamic "secret_environment_variables" {\n'
        '      for_each = var.secret_environment_variables\n'
        '      content {\n'
        '        key        = secret_environment_variables.key\n'
        '        project_id = var.project_id\n'
        '        secret     = secret_environment_variables.value.secret\n'
        '        version    = secret_environment_variables.value.version\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '\n'
        '  labels = local.common_labels\n'
        '\n'
        '  depends_on = [\n'
        '    google_project_iam_member.runtime_roles,\n'
        '    google_secret_manager_secret_iam_member.secret_access,\n'
        '  ]\n'
        '}\n'
        '"""\n'
    )
    new_service_config_tail = (
        '    vpc_connector = var.vpc_connector\n'
        '    vpc_connector_egress_settings = (\n'
        '      var.vpc_connector != null ? var.vpc_connector_egress_settings : null\n'
        '    )\n'
        '\n'
        '    dynamic "secret_environment_variables" {\n'
        '      for_each = var.secret_environment_variables\n'
        '      content {\n'
        '        key        = secret_environment_variables.key\n'
        '        project_id = var.project_id\n'
        '        secret     = secret_environment_variables.value.secret\n'
        '        version    = secret_environment_variables.value.version\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '\n'
        '  labels = local.common_labels\n'
        '\n'
        '  depends_on = [\n'
        '    google_project_iam_member.runtime_roles,\n'
        '    google_secret_manager_secret_iam_member.secret_access,\n'
        '    time_sleep.wait_for_runtime_sa_propagation,\n'
        '  ]\n'
        '}\n'
        '"""\n'
    )

    if "time_sleep.wait_for_runtime_sa_propagation" in content and (
        "vpc_connector != null ? var.vpc_connector_egress_settings : null"
        in content
    ):
        print(
            "[skip] vpc_connector_egress_settings fix and depends_on "
            "update already present"
        )
    elif old_service_config_tail in content:
        content = content.replace(
            old_service_config_tail, new_service_config_tail, 1
        )
        changes_made.append(
            "fixed vpc_connector_egress_settings to be conditional, "
            "added time_sleep to depends_on"
        )
    else:
        print(
            "[warn] could not find the expected service_config block to "
            "patch -- it may already differ from what this script "
            "expects. Skipping this fix; check the file manually."
        )

    # Fix 3: add the time_sleep resource itself, right after the service
    # account definition in IAM_TEMPLATE.
    old_iam_head = (
        'resource "google_service_account" "runtime" {\n'
        '  project      = var.project_id\n'
        '  account_id   = substr("$${var.function_name}-runtime", 0, 30)\n'
        '  display_name = "$${var.function_name} Cloud Functions runtime"\n'
        '  description  = "Dedicated runtime identity for Cloud Function '
        '$${var.function_name}."\n'
        '}\n'
        '\n'
        'resource "google_project_iam_member" "runtime_roles" {\n'
    )
    new_iam_head = (
        'resource "google_service_account" "runtime" {\n'
        '  project      = var.project_id\n'
        '  account_id   = substr("$${var.function_name}-runtime", 0, 30)\n'
        '  display_name = "$${var.function_name} Cloud Functions runtime"\n'
        '  description  = "Dedicated runtime identity for Cloud Function '
        '$${var.function_name}."\n'
        '}\n'
        '\n'
        '# IAM changes, including newly-created service accounts, are\n'
        '# eventually consistent in GCP. Without this buffer, Cloud Run\n'
        '# (which backs Cloud Functions 2nd gen) can intermittently reject\n'
        '# the function creation with "Permission '
        "'iam.serviceaccounts.actAs' denied\"\n"
        '# even though Terraform already reported the service account as\n'
        '# created.\n'
        'resource "time_sleep" "wait_for_runtime_sa_propagation" {\n'
        '  depends_on      = [google_service_account.runtime]\n'
        '  create_duration = "30s"\n'
        '}\n'
        '\n'
        'resource "google_project_iam_member" "runtime_roles" {\n'
    )

    if 'resource "time_sleep" "wait_for_runtime_sa_propagation"' in content:
        print("[skip] time_sleep resource already present")
    elif old_iam_head in content:
        content = content.replace(old_iam_head, new_iam_head, 1)
        changes_made.append("added time_sleep resource to IAM_TEMPLATE")
    else:
        print(
            "[warn] could not find the expected IAM_TEMPLATE service "
            "account block to patch -- it may already differ from what "
            "this script expects. Skipping this fix; check the file "
            "manually."
        )

    if content == original_content:
        print(
            "\nNo changes were written. Either everything was already "
            "patched, or the file's current content doesn't match what "
            "this script expects (see [warn] messages above)."
        )
        return

    TARGET.write_text(content, encoding="utf-8")

    print(f"\nPatched {TARGET}. Changes applied:")
    for change in changes_made:
        print(f"  - {change}")


if __name__ == "__main__":
    main()

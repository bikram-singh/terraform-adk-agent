"""Opt-in live apply, verification, and destroy test for Secret Manager."""

from __future__ import annotations

import os
import subprocess
import time
import shutil
from pathlib import Path
from typing import Any

import pytest

from terraform_agent.generators.base import GeneratorContext
from terraform_agent.generators.secret_manager.generator import (
    SecretManagerGenerator,
)
from tests.e2e.terraform_runner import TerraformRunner


WORKSPACE_NAME = "secret-manager-live-e2e-test"


def _live_testing_enabled() -> bool:
    return os.getenv(
        "TERRAFORM_E2E_LIVE",
        "",
    ).strip().lower() in {"1", "true", "yes"}


def _run_gcloud(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Google Cloud CLI in a cross-platform manner."""

    gcloud_binary = shutil.which("gcloud") or shutil.which("gcloud.cmd")

    if not gcloud_binary:
        pytest.fail(
            "Google Cloud CLI was not found in PATH. "
            "Confirm that 'gcloud --version' works in this terminal."
        )

    return subprocess.run(
        [gcloud_binary, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )

@pytest.mark.skipif(
    not _live_testing_enabled(),
    reason=(
        "Live Terraform E2E testing is disabled. "
        "Set TERRAFORM_E2E_LIVE=true to enable it."
    ),
)
def test_secret_manager_live_apply_verify_and_destroy() -> None:
    """Create real secrets, verify them, and always destroy them."""

    project_id = os.getenv("SECRET_MANAGER_E2E_PROJECT_ID", "").strip()

    if not project_id:
        pytest.skip(
            "SECRET_MANAGER_E2E_PROJECT_ID is not configured."
        )

    suffix = os.getenv(
        "SECRET_MANAGER_E2E_SUFFIX",
        str(int(time.time())),
    ).strip()

    secret_ids = [
        f"tf-adk-e2e-api-token-{suffix}",
        f"tf-adk-e2e-database-password-{suffix}",
    ]

    repository_root = Path(__file__).resolve().parents[2]
    workspace = repository_root / "generated" / WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)

    generator = SecretManagerGenerator()
    generated = generator.generate(
        GeneratorContext(
            workspace_name=WORKSPACE_NAME,
            values={
                "region": "asia-south1",
                "secret_ids": secret_ids,
                "replication_locations": [],
                # No IAM members are required for lifecycle verification.
                "accessor_members": [],
                "environment": "e2e",
                "owner": "platform-team",
                "application": "terraform-adk-agent",
            },
        )
    )

    for filename, content in generated.files.items():
        (workspace / filename).write_text(content, encoding="utf-8")

    variables: dict[str, Any] = {
        "project_id": project_id,
        "region": "asia-south1",
        "secret_ids": secret_ids,
        "replication_locations": [],
        "accessor_members": [],
        "environment": "e2e",
        "owner": "platform-team",
        "application": "terraform-adk-agent",
    }

    runner = TerraformRunner(workspace)

    runner.init()

    apply_completed = False

    try:
        apply_result = runner.apply(variables=variables)
        assert apply_result.return_code == 0
        apply_completed = True

        for secret_id in secret_ids:
            describe_result = _run_gcloud(
                "secrets",
                "describe",
                secret_id,
                "--project",
                project_id,
                "--format=value(name)",
            )

            assert describe_result.returncode == 0, (
                describe_result.stderr
            )
            assert secret_id in describe_result.stdout

    finally:
        # Destroy is attempted even when verification fails after apply.
        if apply_completed:
            destroy_result = runner.destroy(variables=variables)
            assert destroy_result.return_code == 0

            for secret_id in secret_ids:
                describe_result = _run_gcloud(
                    "secrets",
                    "describe",
                    secret_id,
                    "--project",
                    project_id,
                    "--format=value(name)",
                )

                assert describe_result.returncode != 0

"""Shared pytest fixtures for Terraform end-to-end tests."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from .terraform_runner import TerraformRunner


@pytest.fixture(scope="session")
def repository_root() -> Path:
    """Return the repository root directory."""

    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def terraform_binary() -> str:
    """Return the Terraform executable used by E2E tests."""

    configured_binary = os.getenv("TERRAFORM_BINARY", "terraform")
    resolved_binary = shutil.which(configured_binary)

    if resolved_binary is None:
        candidate = Path(configured_binary)

        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())

        pytest.skip(
            "Terraform executable was not found. "
            "Add Terraform to PATH or set TERRAFORM_BINARY "
            "to the full terraform.exe path."
        )

    return resolved_binary


@pytest.fixture(scope="session")
def terraform_runner_factory(
    terraform_binary: str,
) -> Callable[[Path], TerraformRunner]:
    """
    Return a reusable factory that creates TerraformRunner instances.

    This fixture is session-scoped because it is stateless and is reused
    by module-scoped fixtures throughout the E2E test suite.
    """

    def factory(working_directory: Path) -> TerraformRunner:
        return TerraformRunner(
            working_directory=working_directory,
            terraform_binary=terraform_binary,
        )

    return factory
"""Reusable Terraform command runner for end-to-end tests.

This module executes Terraform without using a shell, captures command output,
applies safe automation environment variables, and provides reusable methods
for fmt, init, validate, plan, apply, destroy, output, and state inspection.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_TIMEOUT_SECONDS = 600


@dataclass(frozen=True, slots=True)
class TerraformCommandResult:
    """Structured result returned by a Terraform command."""

    command: tuple[str, ...]
    working_directory: Path
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        """Return True when the command exited successfully."""

        return self.return_code == 0

    @property
    def combined_output(self) -> str:
        """Return stdout and stderr as one readable string."""

        sections = [section.strip() for section in (self.stdout, self.stderr) if section.strip()]
        return "\n".join(sections)

    def assert_success(
        self,
        *,
        accepted_return_codes: Iterable[int] = (0,),
    ) -> "TerraformCommandResult":
        """Raise an assertion error when the command did not succeed."""

        accepted_codes = set(accepted_return_codes)

        if self.return_code not in accepted_codes:
            command_text = " ".join(self.command)

            raise AssertionError(
                "Terraform command failed.\n"
                f"Command: {command_text}\n"
                f"Working directory: {self.working_directory}\n"
                f"Return code: {self.return_code}\n"
                f"Standard output:\n{self.stdout or '<empty>'}\n"
                f"Standard error:\n{self.stderr or '<empty>'}"
            )

        return self


@dataclass(frozen=True, slots=True)
class TerraformPlanResult:
    """Result of a Terraform plan executed with detailed exit codes."""

    command_result: TerraformCommandResult
    has_changes: bool

    @property
    def plan_file(self) -> Path | None:
        """Return the generated plan path when the command used -out."""

        command = self.command_result.command

        for argument in command:
            if argument.startswith("-out="):
                return self.command_result.working_directory / argument.removeprefix("-out=")

        return None


class TerraformRunner:
    """Run Terraform commands against one generated workspace."""

    def __init__(
        self,
        working_directory: str | Path,
        *,
        terraform_binary: str | Path | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.working_directory = Path(working_directory).resolve()
        self.timeout_seconds = timeout_seconds
        self.terraform_binary = self._resolve_terraform_binary(terraform_binary)
        self.environment = self._build_environment(environment)

        if not self.working_directory.exists():
            raise FileNotFoundError(
                f"Terraform working directory does not exist: {self.working_directory}"
            )

        if not self.working_directory.is_dir():
            raise NotADirectoryError(
                f"Terraform working directory is not a directory: "
                f"{self.working_directory}"
            )

    @staticmethod
    def _resolve_terraform_binary(
        terraform_binary: str | Path | None,
    ) -> str:
        configured_binary = (
            str(terraform_binary)
            if terraform_binary is not None
            else os.getenv("TERRAFORM_BINARY", "terraform")
        )

        resolved_binary = shutil.which(configured_binary)

        if resolved_binary is None:
            candidate = Path(configured_binary)

            if candidate.exists() and candidate.is_file():
                return str(candidate.resolve())

            raise FileNotFoundError(
                "Terraform executable was not found. Ensure Terraform is in PATH "
                "or set TERRAFORM_BINARY to the full terraform.exe path."
            )

        return resolved_binary

    @staticmethod
    def _build_environment(
        overrides: Mapping[str, str] | None,
    ) -> dict[str, str]:
        environment = os.environ.copy()

        environment.update(
            {
                "TF_IN_AUTOMATION": "1",
                "TF_INPUT": "0",
                "CHECKPOINT_DISABLE": "1",
            }
        )

        if overrides:
            environment.update({key: str(value) for key, value in overrides.items()})

        return environment

    def _run(
        self,
        arguments: Sequence[str],
        *,
        accepted_return_codes: Iterable[int] = (0,),
        timeout_seconds: int | None = None,
    ) -> TerraformCommandResult:
        command = (
            self.terraform_binary,
            *tuple(str(argument) for argument in arguments),
        )

        try:
            completed_process = subprocess.run(
                command,
                cwd=self.working_directory,
                env=self.environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds or self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""

            raise TimeoutError(
                "Terraform command timed out.\n"
                f"Command: {' '.join(command)}\n"
                f"Working directory: {self.working_directory}\n"
                f"Timeout: {timeout_seconds or self.timeout_seconds} seconds\n"
                f"Standard output:\n{stdout or '<empty>'}\n"
                f"Standard error:\n{stderr or '<empty>'}"
            ) from error

        result = TerraformCommandResult(
            command=tuple(command),
            working_directory=self.working_directory,
            return_code=completed_process.returncode,
            stdout=completed_process.stdout,
            stderr=completed_process.stderr,
        )

        return result.assert_success(
            accepted_return_codes=accepted_return_codes,
        )

    def version(self) -> TerraformCommandResult:
        """Return the installed Terraform version."""

        return self._run(("version", "-no-color"))

    def fmt(
        self,
        *,
        check: bool = False,
        recursive: bool = True,
    ) -> TerraformCommandResult:
        """Format Terraform files or verify that formatting is correct."""

        arguments: list[str] = ["fmt", "-no-color"]

        if recursive:
            arguments.append("-recursive")

        if check:
            arguments.extend(("-check", "-diff"))

        return self._run(arguments)

    def init(
        self,
        *,
        backend: bool = False,
        upgrade: bool = False,
        reconfigure: bool = False,
    ) -> TerraformCommandResult:
        """Initialize the Terraform working directory."""

        arguments = [
            "init",
            "-no-color",
            "-input=false",
            f"-backend={'true' if backend else 'false'}",
        ]

        if upgrade:
            arguments.append("-upgrade")

        if reconfigure:
            arguments.append("-reconfigure")

        return self._run(arguments)

    def validate(self) -> TerraformCommandResult:
        """Validate the Terraform configuration."""

        return self._run(("validate", "-no-color"))

    def plan(
        self,
        *,
        var_file: str | Path | None = None,
        plan_file: str | Path | None = "tfplan",
        variables: Mapping[str, Any] | None = None,
        refresh: bool = True,
        lock: bool = True,
    ) -> TerraformPlanResult:
        """Create a Terraform execution plan.

        Terraform detailed exit codes are used:

        0: plan succeeded and no changes were detected
        1: plan failed
        2: plan succeeded and changes were detected
        """

        arguments: list[str] = [
            "plan",
            "-no-color",
            "-input=false",
            "-detailed-exitcode",
            f"-refresh={'true' if refresh else 'false'}",
            f"-lock={'true' if lock else 'false'}",
        ]

        if var_file is not None:
            resolved_var_file = self._resolve_workspace_file(
                var_file,
                description="Terraform variable file",
            )
            arguments.append(f"-var-file={resolved_var_file}")

        if variables:
            for key, value in sorted(variables.items()):
                arguments.extend(("-var", f"{key}={self._terraform_value(value)}"))

        if plan_file is not None:
            resolved_plan_file = self._resolve_output_path(plan_file)
            arguments.append(f"-out={resolved_plan_file}")

        command_result = self._run(
            arguments,
            accepted_return_codes=(0, 2),
        )

        return TerraformPlanResult(
            command_result=command_result,
            has_changes=command_result.return_code == 2,
        )

    def apply(
        self,
        *,
        plan_file: str | Path | None = None,
        var_file: str | Path | None = None,
        variables: Mapping[str, Any] | None = None,
        auto_approve: bool = True,
    ) -> TerraformCommandResult:
        """Apply a saved plan or create and apply a new plan."""

        arguments: list[str] = [
            "apply",
            "-no-color",
            "-input=false",
        ]

        if auto_approve:
            arguments.append("-auto-approve")

        if plan_file is not None:
            resolved_plan_file = self._resolve_workspace_file(
                plan_file,
                description="Terraform plan file",
            )
            arguments.append(str(resolved_plan_file))
            return self._run(arguments)

        if var_file is not None:
            resolved_var_file = self._resolve_workspace_file(
                var_file,
                description="Terraform variable file",
            )
            arguments.append(f"-var-file={resolved_var_file}")

        if variables:
            for key, value in sorted(variables.items()):
                arguments.extend(("-var", f"{key}={self._terraform_value(value)}"))

        return self._run(arguments)

    def destroy(
        self,
        *,
        var_file: str | Path | None = None,
        variables: Mapping[str, Any] | None = None,
        auto_approve: bool = True,
    ) -> TerraformCommandResult:
        """Destroy resources managed by the Terraform configuration."""

        arguments: list[str] = [
            "destroy",
            "-no-color",
            "-input=false",
        ]

        if auto_approve:
            arguments.append("-auto-approve")

        if var_file is not None:
            resolved_var_file = self._resolve_workspace_file(
                var_file,
                description="Terraform variable file",
            )
            arguments.append(f"-var-file={resolved_var_file}")

        if variables:
            for key, value in sorted(variables.items()):
                arguments.extend(("-var", f"{key}={self._terraform_value(value)}"))

        return self._run(arguments)

    def output(
        self,
        *,
        name: str | None = None,
        json_output: bool = True,
    ) -> TerraformCommandResult:
        """Read Terraform outputs."""

        arguments = ["output", "-no-color"]

        if json_output:
            arguments.append("-json")

        if name:
            arguments.append(name)

        return self._run(arguments)

    def output_json(self) -> dict[str, Any]:
        """Return all Terraform outputs as parsed JSON."""

        result = self.output(json_output=True)

        if not result.stdout.strip():
            return {}

        parsed_output = json.loads(result.stdout)

        if not isinstance(parsed_output, dict):
            raise TypeError(
                "Expected terraform output -json to return a JSON object."
            )

        return parsed_output

    def state_list(self) -> list[str]:
        """Return all resource addresses currently stored in Terraform state."""

        result = self._run(
            ("state", "list", "-no-color"),
            accepted_return_codes=(0, 1),
        )

        if result.return_code == 1:
            no_state_messages = (
                "No state file was found",
                "No state file",
                "does not have any resources",
            )

            if any(message in result.combined_output for message in no_state_messages):
                return []

            result.assert_success()

        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

    def show_json(
        self,
        *,
        plan_file: str | Path | None = None,
    ) -> dict[str, Any]:
        """Return a Terraform plan or state as parsed JSON."""

        arguments = ["show", "-no-color", "-json"]

        if plan_file is not None:
            resolved_plan_file = self._resolve_workspace_file(
                plan_file,
                description="Terraform plan file",
            )
            arguments.append(str(resolved_plan_file))

        result = self._run(arguments)

        if not result.stdout.strip():
            return {}

        parsed_output = json.loads(result.stdout)

        if not isinstance(parsed_output, dict):
            raise TypeError(
                "Expected terraform show -json to return a JSON object."
            )

        return parsed_output

    def _resolve_workspace_file(
        self,
        file_path: str | Path,
        *,
        description: str,
    ) -> Path:
        candidate = Path(file_path)

        if not candidate.is_absolute():
            candidate = self.working_directory / candidate

        candidate = candidate.resolve()

        if not candidate.exists():
            raise FileNotFoundError(f"{description} does not exist: {candidate}")

        if not candidate.is_file():
            raise IsADirectoryError(f"{description} is not a file: {candidate}")

        return candidate

    def _resolve_output_path(self, file_path: str | Path) -> Path:
        candidate = Path(file_path)

        if not candidate.is_absolute():
            candidate = self.working_directory / candidate

        candidate = candidate.resolve()
        candidate.parent.mkdir(parents=True, exist_ok=True)

        return candidate

    @staticmethod
    def _terraform_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"

        if value is None:
            return "null"

        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, separators=(",", ":"))

        return str(value)

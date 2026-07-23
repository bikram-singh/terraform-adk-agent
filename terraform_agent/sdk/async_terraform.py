"""Async, reusable Terraform CLI client.

This is purely additive: it does not replace or modify
`_run_terraform_command` in `terraform_agent.tools.terraform_tools`, or
`TerraformRunner` in the e2e test suite -- both remain fully synchronous
and are what every existing tool, generator, and live test in this
project actually uses today. Nothing here is wired into any existing
code path, so it carries zero regression risk to already-proven
behavior.

The real, concrete capability this adds rather than duplicates: running
several Terraform commands concurrently, in the same or different
workspaces, without blocking on each one in turn. The synchronous tools
can only check one workspace at a time; `run_many` here can check
several at once, for example refresh-only drift plans across every
generated workspace in one call instead of one after another.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import Any, Sequence

from terraform_agent.config import get_settings
from terraform_agent.tools.workspace_tools import get_workspace_path


class AsyncTerraformClient:
    """Async client for running approved Terraform CLI commands inside
    a workspace, with support for running several such commands
    concurrently.
    """

    def __init__(
        self,
        terraform_executable: str | None = None,
        command_timeout_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self._terraform_executable = (
            terraform_executable or settings.terraform_executable
        )
        self._command_timeout_seconds = (
            command_timeout_seconds or settings.terraform_command_timeout
        )

    async def run(
        self,
        workspace_name: str,
        arguments: Sequence[str],
    ) -> dict[str, Any]:
        """Run one Terraform command inside an approved workspace,
        mirroring the return shape of the synchronous
        `_run_terraform_command` for drop-in familiarity."""

        workspace: Path = get_workspace_path(workspace_name)

        if not workspace.exists() or not workspace.is_dir():
            return {
                "status": "error",
                "workspace_name": workspace_name,
                "command": list(arguments),
                "message": f"Workspace does not exist: {workspace_name}",
            }

        command = [self._terraform_executable, *arguments]
        started = time.monotonic()
        process: asyncio.subprocess.Process | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self._command_timeout_seconds,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "workspace_name": workspace_name,
                "command": command,
                "message": (
                    "Terraform executable was not found. "
                    "Check TERRAFORM_EXECUTABLE and PATH."
                ),
            }
        except (asyncio.TimeoutError, TimeoutError):
            if process is not None:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()
            return {
                "status": "error",
                "workspace_name": workspace_name,
                "command": command,
                "message": (
                    "Terraform command exceeded the configured timeout "
                    f"of {self._command_timeout_seconds} seconds."
                ),
            }

        duration = round(time.monotonic() - started, 3)
        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        return {
            "status": "success" if process.returncode == 0 else "error",
            "workspace_name": workspace_name,
            "command": command,
            "return_code": process.returncode,
            "duration_seconds": duration,
            "stdout": stdout,
            "stderr": stderr,
        }

    async def run_many(
        self,
        requests: Sequence[tuple[str, Sequence[str]]],
    ) -> list[dict[str, Any]]:
        """Run several Terraform commands concurrently.

        Each request is an (workspace_name, arguments) pair. Results
        are returned in the same order as the requests, not completion
        order -- a failure or slow command in one workspace does not
        block or reorder the others, since each runs as its own
        subprocess concurrently via asyncio.gather.
        """

        return await asyncio.gather(
            *(
                self.run(workspace_name, arguments)
                for workspace_name, arguments in requests
            )
        )

    async def init(
        self,
        workspace_name: str,
        backend: bool = False,
    ) -> dict[str, Any]:
        arguments = ["init", "-input=false", "-no-color"]
        if not backend:
            arguments.append("-backend=false")
        return await self.run(workspace_name, arguments)

    async def validate(self, workspace_name: str) -> dict[str, Any]:
        return await self.run(
            workspace_name, ["validate", "-no-color", "-json"]
        )

    async def fmt(
        self,
        workspace_name: str,
        check: bool = True,
    ) -> dict[str, Any]:
        arguments = ["fmt", "-no-color", "-recursive"]
        if check:
            arguments.append("-check")
        return await self.run(workspace_name, arguments)

    async def validate_many(
        self,
        workspace_names: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        """Run `terraform init` + `terraform validate` concurrently
        across several workspaces, returning a dict keyed by workspace
        name. Useful for a single "are all my generated projects still
        valid" sweep instead of checking each one in turn."""

        init_results = await asyncio.gather(
            *(self.init(workspace_name) for workspace_name in workspace_names)
        )

        validate_requests = [
            (workspace_name, ["validate", "-no-color", "-json"])
            for workspace_name in workspace_names
        ]
        validate_results = await self.run_many(validate_requests)

        return {
            workspace_name: {
                "initialize": init_result,
                "validate": validate_result,
            }
            for workspace_name, init_result, validate_result in zip(
                workspace_names, init_results, validate_results
            )
        }

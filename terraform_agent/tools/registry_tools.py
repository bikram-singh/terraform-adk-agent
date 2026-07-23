"""Agent-facing tool for the lightweight module registry."""

from __future__ import annotations

from typing import Any

from terraform_agent.intelligence.module_registry import (
    list_available_modules,
)


def list_available_infrastructure_modules() -> dict[str, Any]:
    """
    Return a single, structured inventory of every standalone generator
    and composed architecture recipe this agent can build.

    Each entry includes whether it has actually been proven end-to-end
    against real GCP infrastructure (live_verified), not just locally
    validated with terraform plan/validate. Use this to answer "what
    can you build" accurately, or to check whether a specific service
    or composed recipe is genuinely supported before promising it.
    """

    return list_available_modules()

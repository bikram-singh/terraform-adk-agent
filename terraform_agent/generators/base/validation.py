"""Shared validation helpers for service plugins."""

from __future__ import annotations

import re


_WORKSPACE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$")
_LABEL_PATTERN = re.compile(r"^[a-z0-9_-]{1,63}$")


def require_non_empty(value: str, field_name: str) -> str:
    """Validate a required string."""

    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def validate_workspace_name(value: str) -> str:
    """Validate a generated workspace name."""

    cleaned = require_non_empty(value, "workspace_name")
    if not _WORKSPACE_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "workspace_name must be 3-80 characters and contain only "
            "letters, numbers, hyphens, or underscores."
        )
    return cleaned


def normalize_label_value(value: str, field_name: str) -> str:
    """Normalize and validate a Google Cloud label value."""

    cleaned = value.strip().lower().replace(" ", "-")
    if not _LABEL_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"{field_name} must be 1-63 characters and contain only "
            "lower-case letters, numbers, hyphens, or underscores."
        )
    return cleaned

"""Shared models and validation helpers for Terraform generators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


_LABEL_VALUE_PATTERN = re.compile(r"^[a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class GeneratedProject:
    """Represents files generated for one Terraform project."""

    service: str
    files: Mapping[str, str]


def require_non_empty(value: str, field_name: str) -> str:
    """Validate and return a required non-empty string."""

    cleaned = value.strip()

    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")

    return cleaned


def normalize_label_value(value: str, field_name: str) -> str:
    """Normalize and validate a Google Cloud label value."""

    cleaned = value.strip().lower().replace(" ", "-")

    if not _LABEL_VALUE_PATTERN.fullmatch(cleaned):
        raise ValueError(
            f"{field_name} must contain 1-63 lower-case letters, numbers, "
            "hyphens, or underscores."
        )

    return cleaned
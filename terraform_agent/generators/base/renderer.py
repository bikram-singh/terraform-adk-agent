"""Deterministic template rendering helpers."""

from __future__ import annotations

import re
from typing import Mapping


_PLACEHOLDER_PATTERN = re.compile(
    r"\$(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)"
)


def render_template(
    template: str,
    values: Mapping[str, str],
) -> str:
    """
    Render supported template variables without conflicting with Terraform.

    Supported generator placeholders:

        $region
        $service_name
        $provider_version

    Terraform interpolation escaped as:

        $${var.service_name}

    becomes:

        ${var.service_name}

    Other dollar signs, including regular-expression end anchors, are
    preserved.
    """

    def replace_placeholder(match: re.Match[str]) -> str:
        name = match.group("name")

        if name not in values:
            return match.group(0)

        return str(values[name])

    rendered = _PLACEHOLDER_PATTERN.sub(
        replace_placeholder,
        template,
    )

    # Convert escaped Terraform interpolation from $${...} to ${...}.
    rendered = rendered.replace("$$", "$")

    return rendered.strip() + "\n"
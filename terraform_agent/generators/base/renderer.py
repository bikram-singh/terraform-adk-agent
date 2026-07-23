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

def render_hcl_string_list(values: list[str]) -> str:
    """Render a Terraform list-of-strings literal.

    Non-empty lists always render as multi-line HCL, even for a single
    item -- this matches the shape `terraform fmt` itself would produce,
    which matters because the leading `default` keyword's spacing (see
    render_default_assignment) depends on whether the rendered value is
    single-line or multi-line.
    """

    if not values:
        return "[]"

    lines = ",\n".join(f'    "{value}"' for value in values)
    return "[\n" + lines + "\n  ]"


def render_default_assignment(rendered_value: str) -> str:
    """Render a variable block's `default` assignment line with the
    spacing `terraform fmt` actually wants.

    `terraform fmt` aligns `=` signs across consecutive single-line
    attributes within a block (e.g. `description = ...`, `type = ...`,
    `default = ...`), but breaks that alignment group at any value
    spanning multiple lines. A `default` value populated from a
    render_hcl_string_list() call can be either shape depending on
    runtime data -- `[]` (single-line) for an empty list, or a
    multi-line block for a non-empty one -- so the correct spacing
    can't be a fixed template string; it has to be decided here, from
    the actual rendered value.
    """

    if "\n" in rendered_value:
        return f"default = {rendered_value}"

    return f"default     = {rendered_value}"

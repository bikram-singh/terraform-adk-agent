"""Deterministic template rendering for Terraform project files."""

from __future__ import annotations

from string import Template
from typing import Mapping


def render_template(
    template: str,
    values: Mapping[str, str],
) -> str:
    """Render a string template and ensure one final newline."""

    rendered = Template(template).substitute(values)

    return rendered.strip() + "\n"
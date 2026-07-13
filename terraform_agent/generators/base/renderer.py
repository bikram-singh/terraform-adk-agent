"""Deterministic template rendering helpers."""

from __future__ import annotations

from string import Template
from typing import Mapping


def render_template(template: str, values: Mapping[str, str]) -> str:
    """Render a string template and normalize the final newline."""

    return Template(template).substitute(values).strip() + "\n"

"""Base generator framework."""

from terraform_agent.generators.base.contracts import (
    GeneratedProject,
    GeneratorContext,
    ServiceMetadata,
    TerraformGenerator,
)
from terraform_agent.generators.base.renderer import (
    render_default_assignment,
    render_hcl_string_list,
    render_template,
)

__all__ = [
    "GeneratedProject",
    "GeneratorContext",
    "ServiceMetadata",
    "TerraformGenerator",
    "render_default_assignment",
    "render_hcl_string_list",
    "render_template",
]

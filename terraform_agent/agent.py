"""Root ADK agent with generators and structured Registry services."""

from google.adk.agents import Agent

from terraform_agent.config import get_settings
from terraform_agent.mcp import terraform_mcp_enabled
from terraform_agent.prompts.system_prompt import SYSTEM_PROMPT
from terraform_agent.services import (
    get_terraform_provider_version,
    get_terraform_resource_guidance,
)
from terraform_agent.tools import (
    create_workspace,
    generate_cloud_run_terraform_project,
    generate_gcs_terraform_project,
    generate_gke_terraform_project,
    list_generated_files,
    list_workspaces,
    read_generated_file,
    terraform_format,
    terraform_full_validation,
    terraform_initialize,
    terraform_validate,
    write_generated_file,
)


settings = get_settings()

agent_tools = [
    generate_gcs_terraform_project,
    generate_cloud_run_terraform_project,
    generate_gke_terraform_project,
    create_workspace,
    list_workspaces,
    write_generated_file,
    read_generated_file,
    list_generated_files,
    terraform_format,
    terraform_initialize,
    terraform_validate,
    terraform_full_validation,
]

if terraform_mcp_enabled():
    agent_tools.extend(
        [
            get_terraform_provider_version,
            get_terraform_resource_guidance,
        ]
    )


root_agent = Agent(
    name="terraform_platform_agent",
    model=settings.adk_model,
    description=(
        "Terraform Platform Agent with secure GCS, Cloud Run, and GKE "
        "generation, local validation, and structured Registry guidance."
    ),
    instruction=SYSTEM_PROMPT,
    tools=agent_tools,
)

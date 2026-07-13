"""Root ADK agent for Terraform project generation and validation."""
from google.adk.agents import Agent
from terraform_agent.config import get_settings
from terraform_agent.prompts.system_prompt import SYSTEM_PROMPT
from terraform_agent.tools import (
    create_workspace,
    generate_cloud_run_terraform_project,
    generate_gcs_terraform_project,
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

root_agent = Agent(
    name="terraform_platform_agent",
    model=settings.adk_model,
    description=(
        "Terraform Platform Agent for secure GCS and Cloud Run "
        "configuration generation and local validation."
    ),
    instruction=SYSTEM_PROMPT,
    tools=[
        generate_gcs_terraform_project,
        generate_cloud_run_terraform_project,
        create_workspace,
        list_workspaces,
        write_generated_file,
        read_generated_file,
        list_generated_files,
        terraform_format,
        terraform_initialize,
        terraform_validate,
        terraform_full_validation,
    ],
)

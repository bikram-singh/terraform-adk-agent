"""Root ADK agent with generators and structured Registry services."""

from google.adk.agents import Agent
from google.genai import types

from terraform_agent.config import get_settings
from terraform_agent.mcp import terraform_mcp_enabled
from terraform_agent.prompts.system_prompt import SYSTEM_PROMPT
from terraform_agent.services import (
    get_terraform_provider_version,
    get_terraform_resource_guidance,
)

from terraform_agent.tools import (
    assemble_private_cloud_run_postgres_platform,
    create_workspace,
    design_infrastructure_platform,
    generate_bigquery_terraform_project,
    generate_cloud_functions_terraform_project,
    generate_cloud_run_terraform_project,
    generate_cloud_sql_terraform_project,
    generate_gcs_terraform_project,
    generate_gke_terraform_project,
    generate_iam_terraform_project,
    generate_network_terraform_project,
    generate_pubsub_terraform_project,
    generate_secret_manager_terraform_project,
    list_generated_files,
    list_workspaces,
    plan_terraform_architecture,
    read_generated_file,
    terraform_apply,
    terraform_format,
    terraform_full_validation,
    terraform_initialize,
    terraform_plan,
    terraform_validate,
    write_generated_file,
)


settings = get_settings()

agent_tools = [
    design_infrastructure_platform,
    assemble_private_cloud_run_postgres_platform,
    generate_gcs_terraform_project,
    generate_cloud_run_terraform_project,
    generate_cloud_sql_terraform_project,
    generate_gke_terraform_project,
    generate_network_terraform_project,
    generate_secret_manager_terraform_project,
    generate_iam_terraform_project,
    generate_cloud_functions_terraform_project,
    generate_pubsub_terraform_project,
    generate_bigquery_terraform_project,
    plan_terraform_architecture,
    create_workspace,
    list_workspaces,
    write_generated_file,
    read_generated_file,
    list_generated_files,
    terraform_format,
    terraform_initialize,
    terraform_validate,
    terraform_full_validation,
    terraform_plan,
    terraform_apply,
]

if terraform_mcp_enabled():
    agent_tools.extend(
        [
            get_terraform_provider_version,
            get_terraform_resource_guidance,
        ]
    )


root_agent = Agent(
    name="terraform_agent",
    model=settings.adk_model,
    instruction=SYSTEM_PROMPT,
    tools=[
        *agent_tools,
    ],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                initial_delay=2,
                attempts=5,
            )
        )
    ),
)

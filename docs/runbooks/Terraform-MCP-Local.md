# Terraform MCP Local Runbook

Install the Python dependency:

    pip install mcp

Add `mcp` to `requirements.txt`.

Prepare Docker:

    docker version
    docker pull hashicorp/terraform-mcp-server:1.0.0

Enable in `.env`:

    TERRAFORM_MCP_ENABLED=true
    TERRAFORM_MCP_DOCKER_IMAGE=hashicorp/terraform-mcp-server:1.0.0
    TERRAFORM_MCP_TIMEOUT_SECONDS=60

Start:

    adk web .

Test prompt:

    Use Terraform MCP to find the latest hashicorp/google provider version
    and retrieve documentation for google_cloud_run_v2_service. Summarize
    security-relevant arguments. Do not generate or deploy infrastructure.

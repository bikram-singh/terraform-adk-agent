"""Standalone launcher for the Terraform MCP Server.

Point an MCP client's config directly at this file (not at the
terraform_agent package via -m), so the server starts correctly
regardless of the client's working directory or whether it reliably
passes through PYTHONPATH/env/cwd settings -- some MCP clients don't.

This script adds the project root to sys.path itself, in code, before
importing anything from terraform_agent, which removes any dependency
on how the parent process configured the environment.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from terraform_agent.mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()

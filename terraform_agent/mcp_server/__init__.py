"""MCP server exposing a safety-scoped subset of this agent's tools.

See server.py's module docstring for exactly what is and isn't exposed,
and why.
"""

from terraform_agent.mcp_server.server import main, mcp

__all__ = ["main", "mcp"]

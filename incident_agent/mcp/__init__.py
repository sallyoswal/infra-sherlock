"""Minimal MCP integration surface for Infra Sherlock."""

from incident_agent.mcp.wrapper import (
    get_investigate_tool_spec,
    investigate_incident_tool,
    serialize_incident_report,
)
from incident_agent.mcp.server import create_mcp_app, run_stdio_server

__all__ = [
    "get_investigate_tool_spec",
    "investigate_incident_tool",
    "serialize_incident_report",
    "create_mcp_app",
    "run_stdio_server",
]

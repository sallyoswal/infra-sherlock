"""Minimal MCP integration surface for Infra Sherlock."""

from incident_agent.mcp.wrapper import (
    get_investigate_tool_spec,
    investigate_incident_tool,
    serialize_incident_report,
)

__all__ = [
    "get_investigate_tool_spec",
    "investigate_incident_tool",
    "serialize_incident_report",
]

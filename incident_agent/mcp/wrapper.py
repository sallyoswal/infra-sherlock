"""Minimal MCP-compatible wrapper around the incident investigator.

This module intentionally avoids taking a hard dependency on any MCP SDK.
It exposes a tool-like function and JSON-schema-style metadata so the project
can be plugged into an MCP server later with minimal glue code.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from incident_agent.agent import investigate_incident
from incident_agent.models import IncidentReport


def serialize_incident_report(report: IncidentReport) -> dict[str, Any]:
    """Serialize `IncidentReport` into a JSON-safe dictionary."""
    return asdict(report)


def get_investigate_tool_spec() -> dict[str, Any]:
    """Return MCP-style metadata for the investigation tool."""
    return {
        "name": "investigate_incident",
        "description": (
            "Investigate a local incident dataset and return a structured incident report."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_name": {
                    "type": "string",
                    "description": "Incident scenario directory name under datasets/incidents.",
                }
            },
            "required": ["incident_name"],
            "additionalProperties": False,
        },
    }


def investigate_incident_tool(
    incident_name: str,
    datasets_root: Path | None = None,
    prefer_llm: bool = True,
) -> dict[str, Any]:
    """MCP tool entrypoint that returns a structured incident report payload.

    Args:
        incident_name: Local incident scenario name.
        datasets_root: Optional override for datasets root directory.
        prefer_llm: Whether to attempt LLM synthesis when API key is present.

    Returns:
        JSON-safe dictionary matching `IncidentReport` fields.
    """
    cleaned_name = incident_name.strip()
    if not cleaned_name:
        raise ValueError("incident_name must be a non-empty string")

    report = investigate_incident(
        incident_name=cleaned_name,
        datasets_root=datasets_root,
        prefer_llm=prefer_llm,
    )
    return serialize_incident_report(report)

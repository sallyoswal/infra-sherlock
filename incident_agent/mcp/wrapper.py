"""MCP-compatible wrapper around incident investigation orchestration."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from incident_agent.agent import investigate_incident
from incident_agent.models import IncidentReport


def serialize_incident_report(report: IncidentReport) -> dict[str, Any]:
    """Serialize `IncidentReport` into a JSON-safe dictionary."""
    return asdict(report)


def get_investigate_tool_spec() -> dict[str, Any]:
    """Return MCP-style metadata for the investigation tool."""
    return {
        "name": "investigate_incident",
        "description": "Investigate an incident in local or cloud mode and return a structured report.",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_name": {
                    "type": "string",
                    "description": "Incident identifier (fixture name in local mode; alert/incident ID in cloud mode).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["local", "cloud"],
                    "description": "Investigation mode. Cloud mode requires service_name.",
                },
                "service_name": {
                    "type": "string",
                    "description": "Service identifier used by cloud collectors; required when mode=cloud.",
                },
                "incident_title": {
                    "type": "string",
                    "description": "Optional cloud-mode title override for report metadata.",
                },
            },
            "required": ["incident_name"],
            "additionalProperties": False,
        },
    }


def investigate_incident_tool(
    incident_name: str,
    datasets_root: Path | None = None,
    mode: str = "local",
    service_name: str | None = None,
    incident_title: str | None = None,
) -> dict[str, Any]:
    """MCP tool entrypoint that returns a structured incident report payload.

    Args:
        incident_name: Incident identifier.
        datasets_root: Optional override for datasets root directory (local mode only).
        mode: Investigation mode (`local` or `cloud`).
        service_name: Required in cloud mode.
        incident_title: Optional report title override in cloud mode.

    Returns:
        JSON-safe dictionary matching `IncidentReport` fields.
    """
    cleaned_name = incident_name.strip()
    if not cleaned_name:
        raise ValueError("incident_name must be a non-empty string")
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"local", "cloud"}:
        raise ValueError("mode must be either 'local' or 'cloud'")
    if normalized_mode == "cloud" and not (service_name and service_name.strip()):
        raise ValueError("service_name is required when mode='cloud'")
    investigation_mode: Literal["local", "cloud"] = normalized_mode

    report = investigate_incident(
        incident_name=cleaned_name,
        datasets_root=datasets_root,
        investigation_mode=investigation_mode,
        service_name=service_name.strip() if service_name else None,
        incident_title=incident_title.strip() if incident_title else None,
    )
    return serialize_incident_report(report)

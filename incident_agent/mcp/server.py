"""Real MCP server for Infra Sherlock using the MCP Python SDK."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from incident_agent.agent import investigate_incident


def _extract_timeline(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = report_payload.get("timeline", [])
    if not isinstance(timeline, list):
        return []
    return [entry for entry in timeline if isinstance(entry, dict)]


def _extract_remediation(report_payload: dict[str, Any]) -> list[str]:
    steps = report_payload.get("suggested_remediation", [])
    if not isinstance(steps, list):
        return []
    return [str(item) for item in steps]


def create_mcp_app(datasets_root: Path | None = None):
    """Create and return a configured FastMCP app."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError(
            "MCP SDK is not installed. Install with: pip install mcp"
        ) from exc

    app = FastMCP("infra-sherlock")

    @app.tool(
        name="investigate_incident",
        description="Investigate an incident and return a structured report.",
    )
    def investigate_incident_tool(incident_name: str) -> dict[str, Any]:
        report = investigate_incident(
            incident_name=incident_name,
            datasets_root=datasets_root,
        )
        return {
            "incident_name": report.incident_name,
            "incident_title": report.incident_title,
            "service_name": report.service_name,
            "likely_root_cause": report.likely_root_cause,
            "confidence": report.confidence,
            "key_evidence": report.key_evidence,
            "timeline": [
                {
                    "timestamp": event.timestamp,
                    "event": event.event,
                    "source": event.source,
                }
                for event in report.timeline
            ],
            "suggested_remediation": report.suggested_remediation,
            "next_investigative_steps": report.next_investigative_steps,
        }

    @app.tool(
        name="get_incident_timeline",
        description="Return timeline entries for a specific incident.",
    )
    def get_incident_timeline(incident_name: str) -> list[dict[str, Any]]:
        payload = investigate_incident_tool(incident_name)
        return _extract_timeline(payload)

    @app.tool(
        name="get_incident_remediation",
        description="Return suggested remediation steps for a specific incident.",
    )
    def get_incident_remediation(incident_name: str) -> list[str]:
        payload = investigate_incident_tool(incident_name)
        return _extract_remediation(payload)

    return app


def run_stdio_server(datasets_root: Path | None = None) -> None:
    """Run the MCP server over stdio transport."""
    app = create_mcp_app(datasets_root=datasets_root)
    app.run(transport="stdio")


if __name__ == "__main__":
    run_stdio_server()

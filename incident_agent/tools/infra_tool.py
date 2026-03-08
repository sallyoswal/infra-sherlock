"""Infrastructure change analysis tool."""

from __future__ import annotations

from pathlib import Path

from incident_agent.loader import load_json
from incident_agent.models import InfraAnalysis, InfraChange


class InfraToolError(Exception):
    """Raised when infrastructure change data is missing or malformed."""


def analyze_infra_changes(infra_path: Path) -> InfraAnalysis:
    """Analyze infrastructure changes and identify high-risk events."""
    if not infra_path.exists():
        raise InfraToolError(f"Infra change file not found: {infra_path}")

    payload = load_json(infra_path)
    if not isinstance(payload, list):
        raise InfraToolError(f"Expected list in infra change file: {infra_path}")

    changes = [
        InfraChange(
            timestamp=item["timestamp"],
            component=item["component"],
            change_type=item["change_type"],
            risk_level=item["risk_level"],
            details=item.get("details", ""),
        )
        for item in payload
    ]
    latest = max(changes, key=lambda c: c.timestamp) if changes else None
    high_risk = [c for c in changes if c.risk_level.lower() == "high"]
    return InfraAnalysis(changes=changes, latest_change=latest, high_risk_changes=high_risk)

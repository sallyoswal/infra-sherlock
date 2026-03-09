"""Deploy history analysis tool."""

from __future__ import annotations

from pathlib import Path

from incident_agent.loader import load_json
from incident_agent.models import DeployAnalysis, DeployRecord


class DeployToolError(Exception):
    """Raised when deploy history is missing or malformed."""


def analyze_deploys(deploys_path: Path) -> DeployAnalysis:
    """Analyze deploy history JSON and return the latest deploy."""
    if not deploys_path.exists():
        raise DeployToolError(f"Deploy history file not found: {deploys_path}")

    payload = load_json(deploys_path)
    if not isinstance(payload, list):
        raise DeployToolError(f"Expected list in deploy history file: {deploys_path}")

    try:
        records = [
            DeployRecord(
                timestamp=item["timestamp"],
                version=item["version"],
                service=item["service"],
                notes=item.get("notes", ""),
            )
            for item in payload
        ]
    except (KeyError, TypeError) as exc:
        raise DeployToolError(f"Malformed deploy record in {deploys_path}: {exc}") from exc
    latest = max(records, key=lambda r: r.timestamp) if records else None
    return DeployAnalysis(records=records, latest_deploy=latest)

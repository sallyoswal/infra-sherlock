"""Routing and ownership helpers for incident notifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - import tested via behavior
    yaml = None


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise IncidentDataError(f"Invalid YAML object in {path}")
    return content


def load_routing_config(path: Path | None = None) -> dict[str, Any]:
    """Load service/team routing config used for notifications."""
    target = path or (Path(__file__).resolve().parents[1] / "config" / "routing.yaml")
    return _load_yaml(target)


def route_for_service(service_name: str, routing: dict[str, Any]) -> dict[str, str]:
    """Resolve team and Slack channel for a service."""
    services = routing.get("services", {})
    teams = routing.get("teams", {})
    service_row = services.get(service_name, {})
    team_name = str(service_row.get("team", "incident-command"))
    team_row = teams.get(team_name, {})
    return {
        "team": team_name,
        "slack_channel": str(team_row.get("slack_channel", "#incident-command")),
    }

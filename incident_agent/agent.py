"""Incident investigation orchestrator."""

from __future__ import annotations

from pathlib import Path

from incident_agent.loader import incident_dir, load_json
from incident_agent.models import IncidentMetadata, IncidentReport
from incident_agent.reasoning.deterministic_reasoner import build_report
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics


def investigate_incident(
    incident_name: str,
    datasets_root: Path | None = None,
) -> IncidentReport:
    """Run the full deterministic investigation workflow for an incident."""
    if datasets_root is None:
        datasets_root = Path(__file__).resolve().parents[1] / "datasets" / "incidents"

    target_dir = incident_dir(datasets_root, incident_name)
    metadata_json = load_json(target_dir / "metadata.json")
    metadata = IncidentMetadata(
        incident_name=metadata_json["incident_name"],
        title=metadata_json["title"],
        service_name=metadata_json["service_name"],
    )

    logs = analyze_logs(target_dir / "logs.jsonl")
    metrics = analyze_metrics(target_dir / "metrics.csv")
    deploys = analyze_deploys(target_dir / "deploy_history.json")
    infra = analyze_infra_changes(target_dir / "infra_changes.json")

    return build_report(
        metadata=metadata,
        logs=logs,
        metrics=metrics,
        deploys=deploys,
        infra=infra,
    )

from pathlib import Path

from incident_agent.loader import load_json
from incident_agent.models import IncidentMetadata
from incident_agent.reasoning.deterministic_reasoner import build_report
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics


def test_reasoner_generates_high_confidence_report() -> None:
    base = Path("datasets/incidents/payments_db_timeout")
    metadata_json = load_json(base / "metadata.json")
    metadata = IncidentMetadata(
        incident_name=metadata_json["incident_name"],
        title=metadata_json["title"],
        service_name=metadata_json["service_name"],
    )

    report = build_report(
        metadata=metadata,
        logs=analyze_logs(base / "logs.jsonl"),
        metrics=analyze_metrics(base / "metrics.csv"),
        deploys=analyze_deploys(base / "deploy_history.json"),
        infra=analyze_infra_changes(base / "infra_changes.json"),
    )

    assert "network" in report.likely_root_cause.lower() or "db" in report.likely_root_cause.lower()
    assert report.confidence >= 0.7
    assert len(report.timeline) >= 6


def test_reasoner_timeline_is_sorted_and_multi_source() -> None:
    base = Path("datasets/incidents/payments_db_timeout")
    metadata_json = load_json(base / "metadata.json")
    metadata = IncidentMetadata(
        incident_name=metadata_json["incident_name"],
        title=metadata_json["title"],
        service_name=metadata_json["service_name"],
    )

    report = build_report(
        metadata=metadata,
        logs=analyze_logs(base / "logs.jsonl"),
        metrics=analyze_metrics(base / "metrics.csv"),
        deploys=analyze_deploys(base / "deploy_history.json"),
        infra=analyze_infra_changes(base / "infra_changes.json"),
    )

    timestamps = [event.timestamp for event in report.timeline]
    assert timestamps == sorted(timestamps)
    sources = {event.source for event in report.timeline}
    assert {"logs", "deploy_history", "infra_changes"}.issubset(sources)

from pathlib import Path

from incident_agent.loader import load_json
from incident_agent.models import (
    DeployAnalysis,
    DeployRecord,
    IncidentMetadata,
    InfraAnalysis,
    InfraChange,
    LogAnalysis,
    MetricsAnalysis,
)
from incident_agent.reasoning.deterministic_reasoner import _infer_root_cause, build_report
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


def test_infer_root_cause_prefers_high_risk_infra_with_timeouts() -> None:
    logs = LogAnalysis(10, 5, 4, None, None, [], [])
    metrics = MetricsAnalysis([], True, True, 1.2, 500.0)
    deploys = DeployAnalysis([], None)
    change = InfraChange(
        timestamp="2026-03-06T09:00:00Z",
        component="db-security-group",
        change_type="network_policy",
        risk_level="high",
        details="tightened ingress",
    )
    infra = InfraAnalysis([change], change, [change])

    cause = _infer_root_cause(logs=logs, metrics=metrics, deploys=deploys, infra=infra)
    assert "High-risk" in cause
    assert "db-security-group" in cause


def test_infer_root_cause_uses_deploy_when_errors_rise() -> None:
    logs = LogAnalysis(10, 2, 0, None, None, [], [])
    metrics = MetricsAnalysis([], True, False, 0.8, 200.0)
    deploy = DeployRecord(
        timestamp="2026-03-08T10:00:00Z",
        version="2026.03.08.2",
        service="checkout-api",
        notes="release",
    )
    deploys = DeployAnalysis([deploy], deploy)
    infra = InfraAnalysis([], None, [])

    cause = _infer_root_cause(logs=logs, metrics=metrics, deploys=deploys, infra=infra)
    assert "Deploy 2026.03.08.2 to checkout-api" in cause


def test_infer_root_cause_reports_unclear_when_signals_are_weak() -> None:
    logs = LogAnalysis(5, 0, 0, None, None, [], [])
    metrics = MetricsAnalysis([], False, False, 0.1, 100.0)
    deploys = DeployAnalysis([], None)
    infra = InfraAnalysis([], None, [])

    cause = _infer_root_cause(logs=logs, metrics=metrics, deploys=deploys, infra=infra)
    assert cause == "Root cause unclear. Insufficient signal correlation. Manual investigation required."

from __future__ import annotations

from pathlib import Path

from incident_agent.agent import investigate_incident
from incident_agent.models import IncidentMetadata
from incident_agent.reasoning.llm_reasoner import _evidence_payload
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics


DATASETS_ROOT = Path(__file__).resolve().parents[1] / "datasets" / "incidents"


def test_reasoner_generates_high_confidence_report() -> None:
    report = investigate_incident(
        incident_name="payments_db_timeout",
        datasets_root=DATASETS_ROOT,
        investigation_mode="local",
    )
    assert "network" in report.likely_root_cause.lower() or "db" in report.likely_root_cause.lower()
    assert report.confidence >= 0.7
    assert len(report.timeline) >= 6


def test_reasoner_timeline_is_sorted_and_multi_source() -> None:
    report = investigate_incident(
        incident_name="payments_db_timeout",
        datasets_root=DATASETS_ROOT,
        investigation_mode="local",
    )
    timestamps = [event.timestamp for event in report.timeline]
    assert timestamps == sorted(timestamps)
    sources = {event.source for event in report.timeline}
    assert {"logs", "deploy_history", "infra_changes"}.issubset(sources)


def test_evidence_payload_uses_real_metric_peaks_for_local_mode() -> None:
    base = DATASETS_ROOT / "payments_db_timeout"
    metadata = IncidentMetadata(
        incident_name="payments_db_timeout",
        title="Payments API timeout spike after network policy change",
        service_name="payments-api",
    )
    logs = analyze_logs(base / "logs.jsonl")
    metrics = analyze_metrics(base / "metrics.csv")
    deploys = analyze_deploys(base / "deploy_history.json")
    infra = analyze_infra_changes(base / "infra_changes.json")

    payload = _evidence_payload(metadata, logs, metrics, deploys, infra)
    assert payload["metrics"]["metrics_unavailable"] is False
    assert payload["metrics"]["peak_error_rate"] == metrics.peak_error_rate
    assert payload["metrics"]["peak_p95_latency_ms"] == metrics.peak_p95_latency_ms


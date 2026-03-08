from __future__ import annotations

from pathlib import Path

from incident_agent.models import IncidentReport
from incident_agent.models import TimelineEvent
from incident_agent.watch import run_watch_iteration, run_watch_loop


def _fake_report() -> IncidentReport:
    return IncidentReport(
        incident_name="payments_db_timeout",
        incident_title="Payments API timeout spike after network policy change",
        service_name="payments-api",
        likely_root_cause="network issue",
        confidence=0.9,
        key_evidence=["evidence"],
        timeline=[TimelineEvent(timestamp="2026-03-06T10:00:00Z", event="event", source="logs")],
        suggested_remediation=["fix"],
        next_investigative_steps=["verify"],
    )


def test_watch_iteration_returns_report(monkeypatch) -> None:
    monkeypatch.setattr("incident_agent.watch.investigate_incident", lambda **kwargs: _fake_report())

    result = run_watch_iteration(
        incident_name="payments_db_timeout",
        datasets_root=Path("."),
    )

    assert result.error is None
    assert result.report is not None
    assert result.report.service_name == "payments-api"


def test_watch_loop_once_runs_all_incidents(monkeypatch) -> None:
    monkeypatch.setattr("incident_agent.watch.investigate_incident", lambda **kwargs: _fake_report())

    results = run_watch_loop(
        incidents=["payments_db_timeout", "payments_db_timeout"],
        datasets_root=Path("."),
        once=True,
    )

    assert len(results) == 2
    assert all(result.report is not None for result in results)

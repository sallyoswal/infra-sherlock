from __future__ import annotations

from incident_agent import agent
from incident_agent.models import IncidentReport, TimelineEvent


def _fake_llm_report() -> IncidentReport:
    return IncidentReport(
        incident_name="payments_db_timeout",
        incident_title="Payments API timeout spike after network policy change",
        service_name="payments-api",
        likely_root_cause="Synthetic LLM root cause",
        confidence=0.88,
        key_evidence=["e1", "e2"],
        timeline=[
            TimelineEvent(
                timestamp="2026-03-06T10:00:00Z",
                event="Synthetic LLM timeline event",
                source="llm",
            )
        ],
        suggested_remediation=["r1"],
        next_investigative_steps=["n1"],
    )


def test_agent_uses_llm_when_api_key_present(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _fake_build_report_with_llm(**kwargs):
        return _fake_llm_report()

    monkeypatch.setattr(agent, "build_report_with_llm", _fake_build_report_with_llm)

    report = agent.investigate_incident("payments_db_timeout")
    assert report.likely_root_cause == "Synthetic LLM root cause"


def test_agent_falls_back_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _raise_llm_error(**kwargs):
        raise agent.LLMReasonerError("simulated failure")

    monkeypatch.setattr(agent, "build_report_with_llm", _raise_llm_error)

    report = agent.investigate_incident("payments_db_timeout")
    assert "network" in report.likely_root_cause.lower() or "db" in report.likely_root_cause.lower()

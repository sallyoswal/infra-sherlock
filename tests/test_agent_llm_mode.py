from __future__ import annotations

import pytest

from incident_agent import agent
from incident_agent.models import IncidentReport, TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence
from incident_agent.plugins.registry import PluginConfig


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
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _fake_build_report_with_llm(**kwargs):
        return _fake_llm_report()

    monkeypatch.setattr(agent, "build_report_with_llm", _fake_build_report_with_llm)

    report = agent.investigate_incident("payments_db_timeout")
    assert report.likely_root_cause == "Synthetic LLM root cause"


def test_agent_raises_when_llm_fails(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def _raise_llm_error(**kwargs):
        raise agent.LLMReasonerError("simulated failure")

    monkeypatch.setattr(agent, "build_report_with_llm", _raise_llm_error)

    with pytest.raises(agent.LLMReasonerError):
        agent.investigate_incident("payments_db_timeout")


def test_agent_cloud_mode_skips_local_dataset(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        agent,
        "load_plugin_config",
        lambda _: PluginConfig(mode="cloud", collectors=["aws_cloudwatch"], notifiers=[]),
    )

    class _FakeCollector:
        def healthcheck(self) -> tuple[bool, str]:
            return True, "ok"

        def collect(self, context: IncidentContext) -> PluginEvidence:
            assert context.service_name == "payments-api"
            return PluginEvidence(
                key_evidence=["CloudWatch: timeout spike observed"],
                timeline_events=[
                    TimelineEvent(
                        timestamp="2026-03-08T14:05:00Z",
                        event="ERROR timeout while processing payment",
                        source="plugin:aws_cloudwatch",
                    )
                ],
            )

    monkeypatch.setattr(agent, "build_collectors", lambda _: [_FakeCollector()])
    monkeypatch.setattr(agent, "build_report_with_llm", lambda **_: _fake_llm_report())
    monkeypatch.setattr(agent, "incident_dir", lambda *_: (_ for _ in ()).throw(AssertionError("local path used")))

    report = agent.investigate_incident(
        "prod-incident-1",
        investigation_mode="cloud",
        service_name="payments-api",
    )
    assert report.likely_root_cause == "Synthetic LLM root cause"


def test_agent_cloud_mode_requires_service_name(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(agent.LLMReasonerError):
        agent.investigate_incident("prod-incident-1", investigation_mode="cloud")

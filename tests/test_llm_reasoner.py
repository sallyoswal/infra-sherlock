from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.models import IncidentMetadata, MetricsAnalysis
import incident_agent.reasoning.llm_reasoner as llm_reasoner
from incident_agent.reasoning.llm_reasoner import (
    LLMReasonerError,
    _call_with_retry,
    _evidence_payload,
    validate_and_build_report,
)
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics


def test_validate_and_build_report_success() -> None:
    metadata = IncidentMetadata(
        incident_name="payments_db_timeout",
        title="Payments API timeout spike after network policy change",
        service_name="payments-api",
    )
    payload = {
        "likely_root_cause": "db network path issue",
        "confidence": 0.82,
        "key_evidence": ["timeouts", "latency spike"],
        "timeline": [
            {
                "timestamp": "2026-03-06T10:00:00Z",
                "event": "error spike",
                "source": "metrics",
            }
        ],
        "suggested_remediation": ["rollback change"],
        "next_investigative_steps": ["check connection stats"],
    }

    report = validate_and_build_report(payload=payload, metadata=metadata)
    assert report.confidence == 0.82
    assert report.timeline[0].source == "metrics"


def test_validate_and_build_report_rejects_missing_keys() -> None:
    metadata = IncidentMetadata(
        incident_name="payments_db_timeout",
        title="Payments API timeout spike after network policy change",
        service_name="payments-api",
    )

    with pytest.raises(LLMReasonerError):
        validate_and_build_report(payload={"confidence": 0.7}, metadata=metadata)


def test_call_with_retry_falls_back_without_response_format() -> None:
    class _Response:
        choices = []

    class _Completions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if "response_format" in kwargs:
                raise RuntimeError("response_format unsupported")
            return _Response()

    class _Client:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": _Completions()})()

    client = _Client()
    response = _call_with_retry(client=client, model="m", messages=[], max_retries=3)
    assert response.choices == []
    assert client.chat.completions.calls == 2


def test_call_with_retry_does_not_retry_non_retriable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _StopError(Exception):
        pass

    class _Completions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            del kwargs
            self.calls += 1
            raise _StopError("fatal")

    class _Client:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(llm_reasoner, "_NON_RETRIABLE_EXCEPTIONS", (_StopError,))
    with pytest.raises(_StopError):
        _call_with_retry(client=_Client(), model="m", messages=[], max_retries=3)


def test_call_with_retry_retries_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Completions:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **kwargs):
            del kwargs
            self.calls += 1
            raise RuntimeError("temporary")

    class _Client:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": _Completions()})()

    sleeps: list[int] = []
    monkeypatch.setattr(llm_reasoner.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(LLMReasonerError):
        _call_with_retry(client=_Client(), model="m", messages=[], max_retries=3)
    assert sleeps == [1, 2]


def test_evidence_payload_marks_metrics_unavailable_without_points() -> None:
    metadata = IncidentMetadata(
        incident_name="prod-incident-1",
        title="Production incident",
        service_name="payments-api",
    )
    logs = analyze_logs(Path("datasets/incidents/payments_db_timeout/logs.jsonl"))
    metrics = MetricsAnalysis(
        points=[],
        error_rate_rising=True,
        latency_rising=True,
        peak_error_rate=0.0,
        peak_p95_latency_ms=0.0,
    )
    deploys = analyze_deploys(Path("datasets/incidents/payments_db_timeout/deploy_history.json"))
    infra = analyze_infra_changes(Path("datasets/incidents/payments_db_timeout/infra_changes.json"))

    payload = _evidence_payload(metadata, logs, metrics, deploys, infra)
    assert payload["metrics"]["metrics_unavailable"] is True
    assert payload["metrics"]["peak_error_rate"] is None
    assert payload["metrics"]["peak_p95_latency_ms"] is None

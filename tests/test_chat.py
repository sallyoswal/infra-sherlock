from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.chat import IncidentChatError, ask_incident_question, create_chat_session
from incident_agent.models import IncidentReport, TimelineEvent


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def create(self, **kwargs):
        return _FakeResponse("Most likely caused by infra networking changes.")


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self) -> None:
        self.chat = _FakeChat()


def _fake_report() -> IncidentReport:
    return IncidentReport(
        incident_name="payments_db_timeout",
        incident_title="Payments API timeout spike after network policy change",
        service_name="payments-api",
        likely_root_cause="Synthetic cause",
        confidence=0.5,
        key_evidence=["e1"],
        timeline=[TimelineEvent(timestamp="2026-03-08T10:00:00Z", event="x", source="plugin")],
        suggested_remediation=["r1"],
        next_investigative_steps=["n1"],
    )


def test_create_chat_session_uses_local_incident_context(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("incident_agent.chat.investigate_incident", lambda **kwargs: _fake_report())
    session = create_chat_session("payments_db_timeout")
    assert session.report.incident_name == "payments_db_timeout"
    assert session.history == []
    assert session.report_json


def test_ask_incident_question_returns_answer_and_updates_history(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("incident_agent.chat.investigate_incident", lambda **kwargs: _fake_report())
    session = create_chat_session("payments_db_timeout")
    answer = ask_incident_question(
        session=session,
        question="What is the likely root cause?",
        client=_FakeClient(),
    )

    assert "infra networking" in answer.lower()
    assert len(session.history) == 2
    assert session.history[0]["role"] == "user"
    assert session.history[1]["role"] == "assistant"


def test_ask_incident_question_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(IncidentChatError):
        create_chat_session("payments_db_timeout")


def test_create_chat_session_supports_cloud_mode_args(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}

    def _fake_investigate_incident(**kwargs):
        captured.update(kwargs)
        return _fake_report()

    monkeypatch.setattr("incident_agent.chat.investigate_incident", _fake_investigate_incident)
    session = create_chat_session(
        incident_name="prod-incident-1",
        datasets_root=Path("."),
        investigation_mode="cloud",
        service_name="payments-api",
        incident_title="PD #123",
    )
    assert session.report.incident_name == "payments_db_timeout"
    assert captured["investigation_mode"] == "cloud"
    assert captured["incident_name"] == "prod-incident-1"
    assert captured["service_name"] == "payments-api"
    assert captured["incident_title"] == "PD #123"

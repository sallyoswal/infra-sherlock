from __future__ import annotations

from pathlib import Path

import cli.chat_agent as chat_agent
from cli.chat_agent import handle_slash_command
from incident_agent.chat import IncidentChatSession
from incident_agent.models import IncidentReport, TimelineEvent


def _fake_report() -> IncidentReport:
    return IncidentReport(
        incident_name="payments_db_timeout",
        incident_title="Payments API timeout spike after network policy change",
        service_name="payments-api",
        likely_root_cause="Network policy change restricted DB access",
        confidence=0.87,
        key_evidence=["DB timeouts observed", "High-risk infra change"],
        timeline=[TimelineEvent(timestamp="2026-03-06T10:00:00Z", event="Error spike", source="metrics")],
        suggested_remediation=["Rollback network change"],
        next_investigative_steps=["Check DB connection stats"],
    )


def test_slash_summary_contains_core_fields() -> None:
    report = _fake_report()
    output = handle_slash_command("/summary", report)

    assert "summarize this incident" in output.lower()
    assert "2-4 lines" in output.lower()


def test_slash_timeline_formats_entries() -> None:
    report = _fake_report()
    output = handle_slash_command("/timeline", report)

    assert "timeline" in output.lower()
    assert "timestamps" in output.lower()


def test_slash_help_returns_command_list() -> None:
    report = _fake_report()
    output = handle_slash_command("/help", report)
    assert "/summary" in output
    assert "/root" in output


def test_slash_export_writes_markdown(tmp_path: Path) -> None:
    report = _fake_report()
    target = tmp_path / "chat-export.md"

    output = handle_slash_command(f"/export {target}", report)

    assert target.exists()
    assert "Exported report to:" in output
    content = target.read_text(encoding="utf-8")
    assert content.startswith("#")
    assert report.incident_title in content


def test_free_text_question_routes_to_llm(monkeypatch) -> None:
    session = IncidentChatSession(report=_fake_report())
    calls: list[str] = []

    monkeypatch.setattr(chat_agent, "has_llm_credentials", lambda: True)
    monkeypatch.setattr(chat_agent, "create_chat_session", lambda **kwargs: session)
    monkeypatch.setattr(chat_agent, "ask_incident_question", lambda **kwargs: calls.append(kwargs["question"]) or "ok")

    inputs = iter(["what happened explain to me like a child", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    code = chat_agent.main(["payments_db_timeout"])
    assert code == 0
    assert len(calls) == 2
    assert "startup overview" in calls[0].lower()
    assert calls[1] == "what happened explain to me like a child"


def test_chat_requires_llm_credentials(monkeypatch) -> None:
    monkeypatch.setattr(chat_agent, "has_llm_credentials", lambda: False)

    code = chat_agent.main(["payments_db_timeout"])
    assert code == 3


def test_chat_cloud_mode_requires_service_name(monkeypatch) -> None:
    monkeypatch.setattr(chat_agent, "has_llm_credentials", lambda: True)
    code = chat_agent.main(["prod-incident-1", "--mode", "cloud"])
    assert code == 2

from __future__ import annotations

import cli.chat_major_incident as major_chat_module
from cli.chat_major_incident import main as major_chat_main
from cli.major_incident import main as major_main


def test_major_incident_triage_cli_returns_success() -> None:
    code = major_main(["triage", "payments_sev1_march_2026"])
    assert code == 0


def test_major_incident_chat_command_flow(monkeypatch) -> None:
    inputs = iter(["/overview", "/services", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    code = major_chat_main(["payments_sev1_march_2026"])
    assert code == 0


def test_major_incident_chat_free_text_routes_to_llm(monkeypatch) -> None:
    calls: list[str] = []
    inputs = iter(["what happened in simple terms?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(
        major_chat_module,
        "ask_major_incident_question",
        lambda session, question, concise=True: calls.append(question) or "ok",
    )
    code = major_chat_main(["payments_sev1_march_2026"])
    assert code == 0
    assert calls == ["what happened in simple terms?"]

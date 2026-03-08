from __future__ import annotations

from pathlib import Path

from cli.chat_agent import handle_slash_command
from incident_agent.agent import investigate_incident


def test_slash_summary_contains_core_fields() -> None:
    report = investigate_incident("payments_db_timeout", prefer_llm=False)
    output = handle_slash_command("/summary", report)

    assert "Incident:" in output
    assert "Service:" in output
    assert "Likely Root Cause:" in output


def test_slash_timeline_formats_entries() -> None:
    report = investigate_incident("payments_db_timeout", prefer_llm=False)
    output = handle_slash_command("/timeline", report)

    assert "Incident Timeline:" in output
    assert "[logs]" in output or "[deploy_history]" in output or "[infra_changes]" in output


def test_slash_export_writes_markdown(tmp_path: Path) -> None:
    report = investigate_incident("payments_db_timeout", prefer_llm=False)
    target = tmp_path / "chat-export.md"

    output = handle_slash_command(f"/export {target}", report)

    assert target.exists()
    assert "Exported report to:" in output
    content = target.read_text(encoding="utf-8")
    assert "# Payments API timeout spike after network policy change" in content

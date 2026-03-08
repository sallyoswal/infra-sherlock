from pathlib import Path

from incident_agent.tools.logs_tool import analyze_logs


def test_analyze_logs_extracts_timeout_signals() -> None:
    logs_path = Path("datasets/incidents/payments_db_timeout/logs.jsonl")
    result = analyze_logs(logs_path)

    assert result.total_events >= 6
    assert result.error_events >= 4
    assert result.db_timeout_events >= 3
    assert result.first_timestamp is not None
    assert result.last_timestamp is not None

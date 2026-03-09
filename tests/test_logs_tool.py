from pathlib import Path

import pytest

from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.logs_tool import LogsToolError

DATASETS_ROOT = Path(__file__).resolve().parents[1] / "datasets" / "incidents"


def test_analyze_logs_extracts_timeout_signals() -> None:
    logs_path = DATASETS_ROOT / "payments_db_timeout" / "logs.jsonl"
    result = analyze_logs(logs_path)

    assert result.total_events >= 6
    assert result.error_events >= 4
    assert result.db_timeout_events >= 3
    assert result.first_timestamp is not None
    assert result.last_timestamp is not None
    assert len(result.timeline_events) >= 4


def test_analyze_logs_skips_malformed_lines(tmp_path: Path) -> None:
    logs_path = tmp_path / "logs.jsonl"
    logs_path.write_text(
        '{"timestamp":"2026-03-06T10:00:00Z","level":"ERROR","message":"db timeout"}\n'
        'not-json\n',
        encoding="utf-8",
    )
    result = analyze_logs(logs_path)
    assert result.total_events == 1
    assert result.error_events == 1
    assert result.db_timeout_events == 1


def test_analyze_logs_raises_when_all_lines_malformed(tmp_path: Path) -> None:
    logs_path = tmp_path / "logs.jsonl"
    logs_path.write_text("bad-line\nanother-bad-line\n", encoding="utf-8")
    with pytest.raises(LogsToolError, match="All log entries malformed"):
        analyze_logs(logs_path)

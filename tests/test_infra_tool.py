from pathlib import Path

import pytest

from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.infra_tool import InfraToolError

DATASETS_ROOT = Path(__file__).resolve().parents[1] / "datasets" / "incidents"


def test_analyze_infra_changes_finds_high_risk_items() -> None:
    infra_path = DATASETS_ROOT / "payments_db_timeout" / "infra_changes.json"
    result = analyze_infra_changes(infra_path)

    assert result.latest_change is not None
    assert len(result.high_risk_changes) >= 1


def test_analyze_infra_changes_raises_tool_error_on_malformed_record(tmp_path: Path) -> None:
    bad_file = tmp_path / "infra_changes.json"
    bad_file.write_text('[{"timestamp":"2026-01-01T00:00:00Z","component":"sg"}]', encoding="utf-8")

    with pytest.raises(InfraToolError, match="Malformed infra change record"):
        analyze_infra_changes(bad_file)

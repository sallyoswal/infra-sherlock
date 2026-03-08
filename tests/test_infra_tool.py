from pathlib import Path

from incident_agent.tools.infra_tool import analyze_infra_changes


def test_analyze_infra_changes_finds_high_risk_items() -> None:
    infra_path = Path("datasets/incidents/payments_db_timeout/infra_changes.json")
    result = analyze_infra_changes(infra_path)

    assert result.latest_change is not None
    assert len(result.high_risk_changes) >= 1

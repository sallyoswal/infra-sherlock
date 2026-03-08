from pathlib import Path

from incident_agent.tools.deploy_tool import analyze_deploys


def test_analyze_deploys_returns_latest_deploy() -> None:
    deploy_path = Path("datasets/incidents/payments_db_timeout/deploy_history.json")
    result = analyze_deploys(deploy_path)

    assert result.latest_deploy is not None
    assert result.latest_deploy.version == "2026.03.06.1"

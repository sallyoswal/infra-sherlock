from pathlib import Path

import pytest

from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.deploy_tool import DeployToolError

DATASETS_ROOT = Path(__file__).resolve().parents[1] / "datasets" / "incidents"


def test_analyze_deploys_returns_latest_deploy() -> None:
    deploy_path = DATASETS_ROOT / "payments_db_timeout" / "deploy_history.json"
    result = analyze_deploys(deploy_path)

    assert result.latest_deploy is not None
    assert result.latest_deploy.version == "2026.03.06.1"


def test_analyze_deploys_raises_tool_error_on_malformed_record(tmp_path: Path) -> None:
    bad_file = tmp_path / "deploy_history.json"
    bad_file.write_text('[{"timestamp":"2026-01-01T00:00:00Z","service":"payments-api"}]', encoding="utf-8")

    with pytest.raises(DeployToolError, match="Malformed deploy record"):
        analyze_deploys(bad_file)

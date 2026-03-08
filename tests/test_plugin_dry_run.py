from __future__ import annotations

from pathlib import Path

from incident_agent.plugins.aws_cloudwatch import AWSCloudWatchPlugin
from incident_agent.plugins.base import IncidentContext
from incident_agent.plugins.datadog import DatadogPlugin


def _context() -> IncidentContext:
    return IncidentContext(
        incident_name="payments_db_timeout",
        service_name="payments-api",
        incident_dir=Path("datasets/incidents/payments_db_timeout"),
    )


def test_aws_plugin_dry_run_works_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("PLUGIN_DRY_RUN", "1")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)

    plugin = AWSCloudWatchPlugin()
    ok, _ = plugin.healthcheck()
    result = plugin.collect(_context())

    assert ok is True
    assert result.key_evidence
    assert "dry-run" in result.key_evidence[0].lower()


def test_datadog_plugin_dry_run_works_without_credentials(monkeypatch) -> None:
    monkeypatch.setenv("PLUGIN_DRY_RUN", "true")
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APP_KEY", raising=False)

    plugin = DatadogPlugin()
    ok, _ = plugin.healthcheck()
    result = plugin.collect(_context())

    assert ok is True
    assert result.key_evidence
    assert "dry-run" in result.key_evidence[0].lower()

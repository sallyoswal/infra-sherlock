from __future__ import annotations

from pathlib import Path

from incident_agent import agent
from incident_agent.plugins.aws_cloudwatch import AWSCloudWatchPlugin
from incident_agent.plugins.base import IncidentContext
from incident_agent.plugins.datadog import DatadogPlugin
from incident_agent.plugins.pagerduty import PagerDutyPlugin
from incident_agent.plugins.registry import PluginConfig, build_collectors, build_notifiers


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls = 0

    def healthcheck(self):
        return True, "ok"

    def notify(self, payload):
        self.calls += 1
        return True, "sent"


def test_registry_local_mode_returns_no_plugins() -> None:
    cfg = PluginConfig(mode="local", collectors=["aws_cloudwatch"], notifiers=["slack"])
    assert build_collectors(cfg) == []
    assert build_notifiers(cfg) == []


def test_registry_cloud_mode_instantiates_known_plugins() -> None:
    cfg = PluginConfig(mode="cloud", collectors=["aws_cloudwatch", "datadog", "pagerduty"], notifiers=["slack"])
    collectors = build_collectors(cfg)
    notifiers = build_notifiers(cfg)

    assert [plugin.name for plugin in collectors] == ["aws_cloudwatch", "datadog", "pagerduty"]
    assert [plugin.name for plugin in notifiers] == ["slack"]


def test_cloud_collectors_with_missing_credentials_are_graceful(monkeypatch) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APP_KEY", raising=False)

    monkeypatch.setattr(
        agent,
        "load_plugin_config",
        lambda _: PluginConfig(mode="cloud", collectors=["aws_cloudwatch", "datadog"], notifiers=[]),
    )

    report = agent.investigate_incident("payments_db_timeout")

    assert all("collector configured" not in event.event.lower() for event in report.timeline)


def test_notification_dedupe_sends_once(monkeypatch, tmp_path: Path) -> None:
    fake_notifier = _FakeNotifier()

    monkeypatch.setattr(agent, "load_plugin_config", lambda _: PluginConfig(mode="cloud", collectors=[], notifiers=["slack"]))
    monkeypatch.setattr(agent, "build_collectors", lambda _: [])
    monkeypatch.setattr(agent, "build_notifiers", lambda _: [fake_notifier])
    monkeypatch.setattr(
        agent,
        "load_routing_config",
        lambda _: {
            "services": {"payments-api": {"team": "payments-platform"}},
            "teams": {"payments-platform": {"slack_channel": "#payments-incidents"}},
        },
    )

    state_path = tmp_path / "alerts.json"

    agent.investigate_incident("payments_db_timeout", notify=True, state_path=state_path)
    agent.investigate_incident("payments_db_timeout", notify=True, state_path=state_path)

    assert fake_notifier.calls == 1


def test_aws_plugin_collects_realistic_events(monkeypatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "y")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    class _FakeLogsClient:
        def filter_log_events(self, **kwargs):
            assert kwargs["logGroupName"] == "/aws/lambda/payments-api"
            return {
                "events": [
                    {"timestamp": 1709892000000, "message": "ERROR db timeout while creating payment"},
                    {"timestamp": 1709892060000, "message": "ERROR upstream timeout"},
                ]
            }

    plugin = AWSCloudWatchPlugin(logs_client_factory=lambda region: _FakeLogsClient())
    context = IncidentContext(
        incident_name="payments_db_timeout",
        service_name="payments-api",
        incident_dir=Path("datasets/incidents/payments_db_timeout"),
    )
    result = plugin.collect(context)

    assert result.key_evidence
    assert "returned 2 matching log events" in result.key_evidence[0]
    assert len(result.timeline_events) == 2
    assert result.timeline_events[0].source == "plugin:aws_cloudwatch"


def test_datadog_plugin_collects_matching_events(monkeypatch) -> None:
    monkeypatch.setenv("DATADOG_API_KEY", "x")
    monkeypatch.setenv("DATADOG_APP_KEY", "y")
    monkeypatch.setenv("DATADOG_SITE", "datadoghq.com")

    payload = (
        b'{\"events\": ['
        b'{\"title\": \"payments-api high latency\", \"text\": \"payments-api timeout spike\", \"date_happened\": 1709892000},'
        b'{\"title\": \"other-service\", \"text\": \"healthy\", \"date_happened\": 1709892060}'
        b"]}"
    )

    plugin = DatadogPlugin(http_get=lambda url, headers: payload)
    context = IncidentContext(
        incident_name="payments_db_timeout",
        service_name="payments-api",
        incident_dir=Path("datasets/incidents/payments_db_timeout"),
    )
    result = plugin.collect(context)

    assert result.key_evidence
    assert "returned 1 matching events" in result.key_evidence[0]
    assert len(result.timeline_events) == 1
    assert result.timeline_events[0].source == "plugin:datadog"


def test_datadog_plugin_includes_service_query_param(monkeypatch) -> None:
    monkeypatch.setenv("DATADOG_API_KEY", "x")
    monkeypatch.setenv("DATADOG_APP_KEY", "y")
    captured = {"url": ""}

    def _fake_get(url: str, headers: dict[str, str]) -> bytes:
        del headers
        captured["url"] = url
        return b'{"events": []}'

    plugin = DatadogPlugin(http_get=_fake_get)
    context = IncidentContext(
        incident_name="prod-incident-1",
        service_name="payments-api",
        incident_dir=Path("."),
    )
    plugin.collect(context)
    assert "query=service%3Apayments-api" in captured["url"]


def test_pagerduty_plugin_collects_matching_incidents(monkeypatch) -> None:
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "x")

    payload = (
        b'{\"incidents\": ['
        b'{\"title\": \"payments-api high error rate\", \"summary\": \"prod incident\", \"status\": \"triggered\", \"urgency\": \"high\", \"created_at\": \"2026-03-08T14:10:00Z\"},'
        b'{\"title\": \"other service alert\", \"summary\": \"healthy\", \"status\": \"acknowledged\", \"urgency\": \"low\", \"created_at\": \"2026-03-08T14:12:00Z\"}'
        b"]}"
    )

    plugin = PagerDutyPlugin(http_get=lambda url, headers: payload)
    context = IncidentContext(
        incident_name="prod-incident-1",
        service_name="payments-api",
        incident_dir=Path("."),
    )
    result = plugin.collect(context)

    assert result.key_evidence
    assert "returned 1 matching incidents" in result.key_evidence[0]
    assert len(result.timeline_events) == 1
    assert result.timeline_events[0].source == "plugin:pagerduty"


def test_pagerduty_plugin_uses_service_id_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "x")
    monkeypatch.setenv("PAGERDUTY_SERVICE_ID", "P123")
    captured = {"url": ""}

    payload = b'{"incidents": []}'

    def _fake_get(url: str, headers: dict[str, str]) -> bytes:
        del headers
        captured["url"] = url
        return payload

    plugin = PagerDutyPlugin(http_get=_fake_get)
    context = IncidentContext(
        incident_name="prod-incident-1",
        service_name="payments-api",
        incident_dir=Path("."),
    )
    plugin.collect(context)
    assert "service_ids%5B%5D=P123" in captured["url"]

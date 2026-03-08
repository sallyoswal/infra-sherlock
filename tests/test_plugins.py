from __future__ import annotations

from pathlib import Path

from incident_agent import agent
from incident_agent.models import IncidentReport, TimelineEvent
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
    cfg = PluginConfig(mode="cloud", collectors=["aws_cloudwatch", "datadog"], notifiers=["slack"])
    collectors = build_collectors(cfg)
    notifiers = build_notifiers(cfg)

    assert [plugin.name for plugin in collectors] == ["aws_cloudwatch", "datadog"]
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

    report = agent.investigate_incident("payments_db_timeout", prefer_llm=False)

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

    agent.investigate_incident("payments_db_timeout", prefer_llm=False, notify=True, state_path=state_path)
    agent.investigate_incident("payments_db_timeout", prefer_llm=False, notify=True, state_path=state_path)

    assert fake_notifier.calls == 1

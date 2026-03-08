"""Plugin registry and config loader."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

from incident_agent.loader import IncidentDataError
from incident_agent.plugins.aws_cloudwatch import AWSCloudWatchPlugin
from incident_agent.plugins.base import EvidencePlugin, NotifierPlugin
from incident_agent.plugins.datadog import DatadogPlugin
from incident_agent.plugins.pagerduty import PagerDutyPlugin
from incident_agent.plugins.slack_notifier import SlackNotifierPlugin

try:
    import yaml
except Exception:  # pragma: no cover - import tested via behavior
    yaml = None


@dataclass
class PluginConfig:
    """Runtime plugin configuration loaded from YAML."""

    mode: str = "local"
    collectors: list[str] = field(default_factory=list)
    notifiers: list[str] = field(default_factory=list)
    max_api_calls_per_run: int = 20


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise IncidentDataError(f"Invalid YAML object in {path}")
    return content


def load_plugin_config(path: Path | None = None) -> PluginConfig:
    """Load plugin config with local-first defaults."""
    target = path or (Path(__file__).resolve().parents[2] / "config" / "plugins.yaml")
    raw = _load_yaml(target)

    mode = os.getenv("PLUGIN_MODE", str(raw.get("mode", "local")))
    return PluginConfig(
        mode=mode,
        collectors=[str(x) for x in raw.get("collectors", [])],
        notifiers=[str(x) for x in raw.get("notifiers", [])],
        max_api_calls_per_run=int(raw.get("max_api_calls_per_run", 20)),
    )


def build_collectors(config: PluginConfig) -> list[EvidencePlugin]:
    """Instantiate enabled collector plugins."""
    if config.mode == "local":
        return []

    plugin_map: dict[str, EvidencePlugin] = {
        "aws_cloudwatch": AWSCloudWatchPlugin(),
        "datadog": DatadogPlugin(),
        "pagerduty": PagerDutyPlugin(),
    }
    return [plugin_map[name] for name in config.collectors if name in plugin_map]


def build_notifiers(config: PluginConfig) -> list[NotifierPlugin]:
    """Instantiate enabled notifier plugins."""
    if config.mode == "local":
        return []

    plugin_map: dict[str, NotifierPlugin] = {
        "slack": SlackNotifierPlugin(),
    }
    return [plugin_map[name] for name in config.notifiers if name in plugin_map]

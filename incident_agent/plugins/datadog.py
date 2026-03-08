"""Optional Datadog evidence plugin."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Callable
from urllib import parse, request

from incident_agent.models import TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence


class DatadogPlugin:
    """Collect lightweight Datadog context when API keys are present."""

    name = "datadog"

    def __init__(self, http_get: Callable[[str, dict[str, str]], bytes] | None = None) -> None:
        self._http_get = http_get or self._default_http_get

    @staticmethod
    def _dry_run_enabled() -> bool:
        return os.getenv("PLUGIN_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}

    def healthcheck(self) -> tuple[bool, str]:
        if self._dry_run_enabled():
            return True, "Datadog dry-run mode enabled"
        api_key = os.getenv("DATADOG_API_KEY", "").strip()
        app_key = os.getenv("DATADOG_APP_KEY", "").strip()
        site = os.getenv("DATADOG_SITE", "datadoghq.com").strip()
        if not (api_key and app_key):
            return False, "Datadog API/App key missing"
        return True, f"Datadog configured on {site}"

    @staticmethod
    def _default_http_get(url: str, headers: dict[str, str]) -> bytes:
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=8) as resp:
            return resp.read()

    def collect(self, context: IncidentContext) -> PluginEvidence:
        ok, detail = self.healthcheck()
        if not ok:
            return PluginEvidence()

        api_key = os.getenv("DATADOG_API_KEY", "").strip()
        app_key = os.getenv("DATADOG_APP_KEY", "").strip()
        site = os.getenv("DATADOG_SITE", "datadoghq.com").strip()
        if self._dry_run_enabled():
            return PluginEvidence(
                key_evidence=[
                    f"Datadog dry-run: would query Events API on {site} for service {context.service_name} (last 15m)."
                ],
                timeline_events=[],
            )
        now = int(datetime.now(timezone.utc).timestamp())
        start = now - 15 * 60
        query = parse.urlencode({"start": start, "end": now})
        url = f"https://api.{site}/api/v1/events?{query}"
        headers = {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key}

        try:
            body = self._http_get(url, headers)
            payload = json.loads(body.decode("utf-8"))
            events = payload.get("events", []) if isinstance(payload, dict) else []
        except Exception as exc:
            return PluginEvidence(
                key_evidence=[f"Datadog event collection failed: {exc}"],
                timeline_events=[],
            )

        matching = []
        needle = context.service_name.lower()
        for event in events:
            if not isinstance(event, dict):
                continue
            text = f"{event.get('title', '')} {event.get('text', '')}".lower()
            if needle in text:
                matching.append(event)

        timeline_events: list[TimelineEvent] = []
        for item in matching[:5]:
            ts = item.get("date_happened", now)
            timestamp = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            title = str(item.get("title", "Datadog event")).strip()
            text = str(item.get("text", "")).strip().replace("\n", " ")
            timeline_events.append(
                TimelineEvent(
                    timestamp=timestamp,
                    event=f"Datadog event: {title} {text[:140]}".strip(),
                    source="plugin:datadog",
                    source_type="cloud",
                    service=context.service_name,
                    event_type="event",
                    summary=detail,
                    severity="warning",
                    evidence_source="cloud",
                    provider="datadog",
                )
            )

        return PluginEvidence(
            key_evidence=[f"Datadog returned {len(matching)} matching events for {context.service_name}."],
            timeline_events=timeline_events,
        )

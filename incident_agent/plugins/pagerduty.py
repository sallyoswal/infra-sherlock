"""Optional PagerDuty evidence plugin."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Callable
from urllib import parse, request

from incident_agent.models import TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence


class PagerDutyPlugin:
    """Collect lightweight PagerDuty incident context when API token is present."""

    name = "pagerduty"

    def __init__(self, http_get: Callable[[str, dict[str, str]], bytes] | None = None) -> None:
        self._http_get = http_get or self._default_http_get

    @staticmethod
    def _dry_run_enabled() -> bool:
        return os.getenv("PLUGIN_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}

    def healthcheck(self) -> tuple[bool, str]:
        if self._dry_run_enabled():
            return True, "PagerDuty dry-run mode enabled"
        token = os.getenv("PAGERDUTY_API_TOKEN", "").strip()
        if not token:
            return False, "PagerDuty API token missing"
        return True, "PagerDuty API token configured"

    @staticmethod
    def _default_http_get(url: str, headers: dict[str, str]) -> bytes:
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=8) as resp:
            return resp.read()

    def collect(self, context: IncidentContext) -> PluginEvidence:
        ok, detail = self.healthcheck()
        if not ok:
            return PluginEvidence()

        token = os.getenv("PAGERDUTY_API_TOKEN", "").strip()
        base_url = os.getenv("PAGERDUTY_API_URL", "https://api.pagerduty.com").strip().rstrip("/")
        if self._dry_run_enabled():
            return PluginEvidence(
                key_evidence=[
                    f"PagerDuty dry-run: would query incidents for service {context.service_name} (statuses=triggered,acknowledged)."
                ],
                timeline_events=[],
            )

        query = parse.urlencode(
            {
                "statuses[]": ["triggered", "acknowledged"],
                "limit": 25,
            },
            doseq=True,
        )
        url = f"{base_url}/incidents?{query}"
        headers = {
            "Authorization": f"Token token={token}",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }

        try:
            body = self._http_get(url, headers)
            payload = json.loads(body.decode("utf-8"))
            incidents = payload.get("incidents", []) if isinstance(payload, dict) else []
        except Exception as exc:
            return PluginEvidence(
                key_evidence=[f"PagerDuty incident collection failed: {exc}"],
                timeline_events=[],
            )

        needle = context.service_name.lower()
        matching: list[dict[str, object]] = []
        for incident in incidents:
            if not isinstance(incident, dict):
                continue
            text = f"{incident.get('title', '')} {incident.get('summary', '')}".lower()
            service = incident.get("service")
            if isinstance(service, dict):
                text += f" {service.get('summary', '')}".lower()
            if needle in text:
                matching.append(incident)

        timeline_events: list[TimelineEvent] = []
        now = datetime.now(timezone.utc)
        for item in matching[:5]:
            created_at = str(item.get("created_at", now.isoformat()))
            title = str(item.get("title", "PagerDuty incident")).strip()
            status = str(item.get("status", "unknown")).strip()
            urgency = str(item.get("urgency", "unknown")).strip()
            timeline_events.append(
                TimelineEvent(
                    timestamp=created_at,
                    event=f"PagerDuty incident: {title} (status={status}, urgency={urgency})",
                    source="plugin:pagerduty",
                    source_type="cloud",
                    service=context.service_name,
                    event_type="incident",
                    summary=detail,
                    severity="warning",
                    evidence_source="cloud",
                    provider="pagerduty",
                )
            )

        return PluginEvidence(
            key_evidence=[
                f"PagerDuty returned {len(matching)} matching incidents for {context.service_name}."
            ],
            timeline_events=timeline_events,
        )


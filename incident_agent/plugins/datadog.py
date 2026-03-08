"""Optional Datadog evidence plugin."""

from __future__ import annotations

import os

from incident_agent.models import TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence


class DatadogPlugin:
    """Collect lightweight Datadog context when API keys are present."""

    name = "datadog"

    def healthcheck(self) -> tuple[bool, str]:
        api_key = os.getenv("DATADOG_API_KEY", "").strip()
        app_key = os.getenv("DATADOG_APP_KEY", "").strip()
        site = os.getenv("DATADOG_SITE", "datadoghq.com").strip()
        if not (api_key and app_key):
            return False, "Datadog API/App key missing"
        return True, f"Datadog configured on {site}"

    def collect(self, context: IncidentContext) -> PluginEvidence:
        ok, detail = self.healthcheck()
        if not ok:
            return PluginEvidence()

        return PluginEvidence(
            key_evidence=["Datadog plugin active (read-only mode)."],
            timeline_events=[
                TimelineEvent(
                    timestamp="1970-01-01T00:00:01Z",
                    event="Datadog collector configured",
                    source="plugin:datadog",
                    source_type="cloud",
                    service=context.service_name,
                    event_type="collector_status",
                    summary=detail,
                    severity="info",
                    evidence_source="cloud",
                    provider="datadog",
                )
            ],
        )

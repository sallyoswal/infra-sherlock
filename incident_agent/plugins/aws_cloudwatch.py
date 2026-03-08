"""Optional AWS CloudWatch evidence plugin.

This v1 connector is intentionally read-only and conservative.
It degrades gracefully when AWS credentials are unavailable.
"""

from __future__ import annotations

import os

from incident_agent.models import TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence


class AWSCloudWatchPlugin:
    """Collect lightweight CloudWatch context when credentials are present."""

    name = "aws_cloudwatch"

    def healthcheck(self) -> tuple[bool, str]:
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        region = os.getenv("AWS_REGION", "").strip()
        if not (access_key and secret_key and region):
            return False, "AWS credentials or region missing"
        return True, f"AWS configured for region {region}"

    def collect(self, context: IncidentContext) -> PluginEvidence:
        ok, detail = self.healthcheck()
        if not ok:
            return PluginEvidence()

        # Keep collection deterministic and non-invasive for v1.
        region = os.getenv("AWS_REGION", "unknown")
        return PluginEvidence(
            key_evidence=[
                f"AWS CloudWatch plugin active in {region} (read-only mode)."
            ],
            timeline_events=[
                TimelineEvent(
                    timestamp="1970-01-01T00:00:00Z",
                    event="AWS CloudWatch collector configured",
                    source="plugin:aws_cloudwatch",
                    source_type="cloud",
                    service=context.service_name,
                    event_type="collector_status",
                    summary=detail,
                    severity="info",
                    evidence_source="cloud",
                    provider="aws",
                )
            ],
        )

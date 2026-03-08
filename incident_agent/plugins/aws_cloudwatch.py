"""Optional AWS CloudWatch evidence plugin.

This connector is read-only and degrades gracefully when credentials/SDK are unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any, Callable

from incident_agent.models import TimelineEvent
from incident_agent.plugins.base import IncidentContext, PluginEvidence


class AWSCloudWatchPlugin:
    """Collect lightweight CloudWatch context when credentials are present."""

    name = "aws_cloudwatch"

    def __init__(self, logs_client_factory: Callable[[str], Any] | None = None) -> None:
        self._logs_client_factory = logs_client_factory

    @staticmethod
    def _dry_run_enabled() -> bool:
        return os.getenv("PLUGIN_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}

    def healthcheck(self) -> tuple[bool, str]:
        if self._dry_run_enabled():
            return True, "AWS dry-run mode enabled"
        access_key = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        region = os.getenv("AWS_REGION", "").strip()
        if not (access_key and secret_key and region):
            return False, "AWS credentials or region missing"
        return True, f"AWS configured for region {region}"

    def _build_client(self, region: str) -> Any:
        if self._logs_client_factory is not None:
            return self._logs_client_factory(region)
        try:
            import boto3
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError("boto3 is required for AWS CloudWatch plugin") from exc
        return boto3.client("logs", region_name=region)

    def collect(self, context: IncidentContext) -> PluginEvidence:
        ok, detail = self.healthcheck()
        if not ok:
            return PluginEvidence()

        region = os.getenv("AWS_REGION", "unknown")
        log_group = os.getenv("AWS_LOG_GROUP", f"/aws/lambda/{context.service_name}")
        if self._dry_run_enabled():
            return PluginEvidence(
                key_evidence=[
                    f"AWS dry-run: would query {log_group} in {region} for timeout/error events (last 15m)."
                ],
                timeline_events=[],
            )
        now = datetime.now(timezone.utc)
        start_ms = int((now.timestamp() - 15 * 60) * 1000)
        end_ms = int(now.timestamp() * 1000)

        try:
            client = self._build_client(region)
            response = client.filter_log_events(
                logGroupName=log_group,
                filterPattern="ERROR ?timeout ?Timeout",
                startTime=start_ms,
                endTime=end_ms,
                limit=20,
            )
            events = response.get("events", []) or []
        except Exception as exc:
            return PluginEvidence(
                key_evidence=[f"AWS CloudWatch collection failed: {exc}"],
                timeline_events=[],
            )

        timeline_events: list[TimelineEvent] = []
        for item in events[:5]:
            ts_ms = int(item.get("timestamp", end_ms))
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
            message = str(item.get("message", "")).strip().replace("\n", " ")
            timeline_events.append(
                TimelineEvent(
                    timestamp=ts,
                    event=f"CloudWatch log: {message[:200]}",
                    source="plugin:aws_cloudwatch",
                    source_type="cloud",
                    service=context.service_name,
                    event_type="log_event",
                    summary=detail,
                    severity="error",
                    evidence_source="cloud",
                    provider="aws",
                )
            )

        return PluginEvidence(
            key_evidence=[f"AWS CloudWatch returned {len(events)} matching log events from {log_group}."],
            timeline_events=timeline_events,
        )

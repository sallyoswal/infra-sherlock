"""Log analysis tool for deterministic incident investigation."""

from __future__ import annotations

import json
from pathlib import Path

from incident_agent.models import LogAnalysis, LogEvent


class LogsToolError(Exception):
    """Raised when logs are missing or malformed."""


def analyze_logs(logs_path: Path) -> LogAnalysis:
    """Analyze JSONL logs and extract timeout/error signals."""
    if not logs_path.exists():
        raise LogsToolError(f"Logs file not found: {logs_path}")

    total_events = 0
    error_events = 0
    db_timeout_events = 0
    first_ts: str | None = None
    last_ts: str | None = None
    timeout_samples: list[str] = []
    timeline_events: list[LogEvent] = []
    malformed = 0

    for raw_line in logs_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue

        total_events += 1
        ts = str(payload.get("timestamp", ""))
        level = str(payload.get("level", "INFO")).upper()
        message = str(payload.get("message", ""))

        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts

        if level in {"ERROR", "CRITICAL"}:
            error_events += 1

        lowered = message.lower()
        if "timeout" in lowered and "db" in lowered:
            db_timeout_events += 1
            if len(timeout_samples) < 3:
                timeout_samples.append(message)

        # Keep timeline-focused log entries: errors/critical, timeout events, and deploy completion markers.
        if (
            level in {"ERROR", "CRITICAL"}
            or ("timeout" in lowered and "db" in lowered)
            or ("deploy" in lowered and "completed" in lowered)
        ):
            timeline_events.append(LogEvent(timestamp=ts, level=level, message=message))

    if total_events == 0 and malformed > 0:
        raise LogsToolError(f"All log entries malformed in {logs_path}")

    return LogAnalysis(
        total_events=total_events,
        error_events=error_events,
        db_timeout_events=db_timeout_events,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        sample_timeout_messages=timeout_samples,
        timeline_events=timeline_events,
    )

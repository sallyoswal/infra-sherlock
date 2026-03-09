"""Incident investigation orchestrator."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import hashlib
import json
from typing import Literal

from incident_agent.loader import incident_dir, load_json
from incident_agent.llm_provider import has_llm_credentials
from incident_agent.models import (
    DeployAnalysis,
    IncidentMetadata,
    IncidentReport,
    InfraAnalysis,
    LogAnalysis,
    LogEvent,
    MetricsAnalysis,
    NotificationPayload,
)
from incident_agent.notifications.state_store import NotificationStateStore
from incident_agent.plugins.base import IncidentContext, PluginEvidence
from incident_agent.plugins.registry import (
    PluginConfig,
    build_collectors,
    build_notifiers,
    load_plugin_config,
)
from incident_agent.reasoning.llm_reasoner import LLMReasonerError, build_report_with_llm
from incident_agent.routing import load_routing_config, route_for_service
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics

MAX_NOTIFICATION_EVIDENCE = 3


def investigate_incident(
    incident_name: str,
    datasets_root: Path | None = None,
    plugin_config_path: Path | None = None,
    routing_config_path: Path | None = None,
    notify: bool = False,
    state_path: Path | None = None,
    investigation_mode: Literal["local", "cloud"] = "local",
    service_name: str | None = None,
    incident_title: str | None = None,
) -> IncidentReport:
    """Run AI-only investigation workflow."""
    if not has_llm_credentials():
        raise LLMReasonerError("AI-only mode requires LLM credentials for investigation.")

    plugin_cfg = load_plugin_config(plugin_config_path)

    if investigation_mode == "cloud":
        if not service_name:
            raise LLMReasonerError("cloud mode requires service_name")

        # Cloud mode must use collectors and must not rely on local dataset files.
        plugin_cfg.mode = "cloud"
        collectors = build_collectors(plugin_cfg)
        if not collectors:
            raise LLMReasonerError("cloud mode requires at least one configured collector plugin")

        context = IncidentContext(
            incident_name=incident_name,
            service_name=service_name,
            incident_dir=Path("."),
        )
        plugin_evidence = _collect_plugin_evidence(
            collectors,
            context,
            max_calls=plugin_cfg.max_api_calls_per_run,
        )
        if not _has_actionable_cloud_evidence(plugin_evidence):
            raise LLMReasonerError(
                "cloud mode collected no actionable evidence; verify plugin credentials, filters, and service_name"
            )
        logs, metrics, deploys, infra = _analyses_from_plugin_evidence(plugin_evidence)
        metadata = IncidentMetadata(
            incident_name=incident_name,
            title=incident_title or f"Cloud incident: {incident_name}",
            service_name=service_name,
        )
        report = build_report_with_llm(
            metadata=metadata,
            logs=logs,
            metrics=metrics,
            deploys=deploys,
            infra=infra,
        )
        _merge_plugin_evidence(report, plugin_evidence)
    else:
        if datasets_root is None:
            datasets_root = Path(__file__).resolve().parents[1] / "datasets" / "incidents"

        target_dir = incident_dir(datasets_root, incident_name)
        metadata_json = load_json(target_dir / "metadata.json")
        metadata = IncidentMetadata(
            incident_name=metadata_json["incident_name"],
            title=metadata_json["title"],
            service_name=metadata_json["service_name"],
        )

        logs = analyze_logs(target_dir / "logs.jsonl")
        metrics = analyze_metrics(target_dir / "metrics.csv")
        deploys = analyze_deploys(target_dir / "deploy_history.json")
        infra = analyze_infra_changes(target_dir / "infra_changes.json")

        report = build_report_with_llm(
            metadata=metadata,
            logs=logs,
            metrics=metrics,
            deploys=deploys,
            infra=infra,
        )

        # Keep local mode fixture-only and avoid mixing cloud plugin evidence.
        plugin_cfg.mode = "local"

    if notify:
        _notify_if_needed(
            report=report,
            plugin_cfg=plugin_cfg,
            routing_config_path=routing_config_path,
            state_path=state_path,
        )

    return report


def _analyses_from_plugin_evidence(
    evidence: PluginEvidence,
) -> tuple[LogAnalysis, MetricsAnalysis, DeployAnalysis, InfraAnalysis]:
    """Build minimal reasoner inputs from plugin evidence for cloud mode."""
    combined = [item.lower() for item in evidence.key_evidence]
    combined.extend(event.event.lower() for event in evidence.timeline_events)

    timeout_samples = [
        text for text in evidence.key_evidence if "timeout" in text.lower()
    ][:3]
    error_events = sum(
        1 for text in combined if ("error" in text or "exception" in text or "fail" in text)
    )
    timeout_events = sum(1 for text in combined if "timeout" in text)

    sorted_timeline = sorted(evidence.timeline_events, key=lambda e: e.timestamp)
    first_ts = sorted_timeline[0].timestamp if sorted_timeline else None
    last_ts = sorted_timeline[-1].timestamp if sorted_timeline else None

    log_events: list[LogEvent] = []
    for event in sorted_timeline:
        lowered = event.event.lower()
        level = "ERROR" if ("error" in lowered or "timeout" in lowered) else "INFO"
        log_events.append(LogEvent(timestamp=event.timestamp, level=level, message=event.event))

    logs = LogAnalysis(
        total_events=len(log_events),
        error_events=error_events,
        db_timeout_events=timeout_events,
        first_timestamp=first_ts,
        last_timestamp=last_ts,
        sample_timeout_messages=timeout_samples,
        timeline_events=log_events,
    )
    metrics = MetricsAnalysis(
        points=[],
        error_rate_rising=error_events > 0,
        latency_rising=timeout_events > 0,
        peak_error_rate=float(error_events),
        peak_p95_latency_ms=float(timeout_events * 100),
    )
    deploys = DeployAnalysis(records=[], latest_deploy=None)
    infra = InfraAnalysis(changes=[], latest_change=None, high_risk_changes=[])
    return logs, metrics, deploys, infra


def _has_actionable_cloud_evidence(evidence: PluginEvidence) -> bool:
    """Return whether collected plugin evidence is sufficient for LLM synthesis."""
    if evidence.timeline_events:
        return True
    for item in evidence.key_evidence:
        lowered = item.lower()
        if "dry-run" in lowered or "failed" in lowered:
            continue
        return True
    return False


def _collect_plugin_evidence(
    collectors: list[object],
    context: IncidentContext,
    max_calls: int,
) -> PluginEvidence:
    """Collect and merge optional evidence from enabled plugins."""
    merged = PluginEvidence()
    budget = max(max_calls, 0)
    calls = 0
    for collector in collectors:
        if calls >= budget:
            break
        ok, _ = collector.healthcheck()
        if not ok:
            continue
        partial = collector.collect(context)
        calls += 1
        merged.key_evidence.extend(partial.key_evidence)
        merged.timeline_events.extend(partial.timeline_events)
    return merged


def _merge_plugin_evidence(report: IncidentReport, evidence: PluginEvidence) -> None:
    """Append plugin evidence while preserving deterministic report ordering."""
    if not evidence.key_evidence and not evidence.timeline_events:
        return
    report.key_evidence.extend(evidence.key_evidence)
    report.timeline.extend(evidence.timeline_events)
    report.timeline.sort(key=lambda event: event.timestamp)


def _build_notification_payload(report: IncidentReport, routing: dict[str, object]) -> NotificationPayload:
    """Build concise notification payload from a report."""
    route = route_for_service(report.service_name, routing)
    return NotificationPayload(
        incident_name=report.incident_name,
        incident_title=report.incident_title,
        service_name=report.service_name,
        likely_root_cause=report.likely_root_cause,
        confidence=report.confidence,
        owner_team=route["team"],
        slack_channel=route["slack_channel"],
        key_evidence=report.key_evidence[:MAX_NOTIFICATION_EVIDENCE],
        next_action=report.suggested_remediation[0] if report.suggested_remediation else "Run standard incident triage.",
    )


def _fingerprint_payload(payload: NotificationPayload) -> str:
    """Create stable fingerprint used for dedupe."""
    canonical = json.dumps(asdict(payload), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _notify_if_needed(
    report: IncidentReport,
    plugin_cfg: PluginConfig,
    routing_config_path: Path | None = None,
    state_path: Path | None = None,
) -> None:
    """Send notifications using enabled notifier plugins with dedupe."""
    notifiers = build_notifiers(plugin_cfg)
    if not notifiers:
        return

    routing = load_routing_config(routing_config_path)
    payload = _build_notification_payload(report, routing)
    fingerprint = _fingerprint_payload(payload)
    state_file = state_path or (Path(__file__).resolve().parents[1] / "state" / "alerts.json")
    state_store = NotificationStateStore(state_file)

    incident_key = f"{payload.incident_name}:{payload.service_name}"
    if state_store.has_sent(incident_key, fingerprint):
        return

    text = (
        f"Infra Sherlock alert: {payload.incident_title}\n"
        f"Service: {payload.service_name}\n"
        f"Owner: {payload.owner_team} ({payload.slack_channel})\n"
        f"Likely cause: {payload.likely_root_cause}\n"
        f"Next action: {payload.next_action}"
    )
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{payload.incident_title}*"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Service:* `{payload.service_name}`  *Confidence:* {payload.confidence:.2f}",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Likely cause:* {payload.likely_root_cause}"}},
    ]
    for item in payload.key_evidence:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"- {item}"}})

    outgoing = {"text": text, "blocks": blocks}
    delivered = False
    for notifier in notifiers:
        ok, _ = notifier.notify(outgoing)
        delivered = delivered or ok
    if delivered:
        state_store.mark_sent(incident_key, fingerprint)

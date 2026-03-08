"""Incident investigation orchestrator."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
import hashlib
import json

from incident_agent.loader import incident_dir, load_json
from incident_agent.llm_provider import has_llm_credentials
from incident_agent.models import IncidentMetadata, IncidentReport, NotificationPayload
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
) -> IncidentReport:
    """Run AI-only investigation workflow."""
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

    if not has_llm_credentials():
        raise LLMReasonerError("AI-only mode requires LLM credentials for investigation.")

    report = build_report_with_llm(
        metadata=metadata,
        logs=logs,
        metrics=metrics,
        deploys=deploys,
        infra=infra,
    )

    plugin_cfg = load_plugin_config(plugin_config_path)
    collectors = build_collectors(plugin_cfg)
    context = IncidentContext(
        incident_name=incident_name,
        service_name=metadata.service_name,
        incident_dir=target_dir,
    )
    plugin_evidence = _collect_plugin_evidence(collectors, context)
    _merge_plugin_evidence(report, plugin_evidence)

    if notify:
        _notify_if_needed(
            report=report,
            plugin_cfg=plugin_cfg,
            routing_config_path=routing_config_path,
            state_path=state_path,
        )

    return report


def _collect_plugin_evidence(collectors: list[object], context: IncidentContext) -> PluginEvidence:
    """Collect and merge optional evidence from enabled plugins."""
    merged = PluginEvidence()
    for collector in collectors:
        ok, _ = collector.healthcheck()
        if not ok:
            continue
        partial = collector.collect(context)
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

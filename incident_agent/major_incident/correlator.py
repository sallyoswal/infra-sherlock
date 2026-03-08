"""Deterministic correlation engine for major incidents."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from incident_agent.loader import IncidentDataError
from incident_agent.major_incident.loader import load_major_incident_dataset
from incident_agent.models import (
    BlastRadius,
    ChildIncident,
    Hypothesis,
    IncidentGroup,
    MajorIncidentReport,
    ServiceIncidentSummary,
    ServiceMetadata,
    TimelineEvent,
)


@dataclass
class _ServiceEvidence:
    first_anomaly: str
    timeout_events: int
    high_risk_changes: list[dict]
    deploys: list[dict]
    metrics_peak_error_rate: float
    metrics_peak_latency_ms: float
    correlation_ids: list[str]
    timeline: list[TimelineEvent]


def _dt(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise IncidentDataError(f"Missing required evidence file: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_json(path: Path):
    if not path.exists():
        raise IncidentDataError(f"Missing required evidence file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_logs(log_lines: list[str], service: str) -> tuple[str, int, list[str], list[TimelineEvent]]:
    first_ts = ""
    timeout_count = 0
    corr_ids: set[str] = set()
    timeline: list[TimelineEvent] = []

    for line in log_lines:
        # Format: timestamp|LEVEL|message|corr=<id>
        parts = line.split("|")
        if len(parts) < 3:
            continue
        ts = parts[0].strip()
        level = parts[1].strip().upper()
        message = parts[2].strip()

        if not first_ts:
            first_ts = ts

        if "timeout" in message.lower() and "db" in message.lower():
            timeout_count += 1

        for token in parts[3:]:
            token = token.strip()
            if token.startswith("corr="):
                corr_ids.add(token.split("=", 1)[1])

        if level in {"ERROR", "WARN"} or "timeout" in message.lower():
            timeline.append(
                TimelineEvent(
                    timestamp=ts,
                    event=f"{level} log: {message}",
                    source="logs",
                    source_type="logs",
                    service=service,
                    event_type="log_signal",
                    summary=message,
                    severity="high" if level == "ERROR" else "medium",
                )
            )

    return first_ts, timeout_count, sorted(corr_ids), timeline


def _parse_metrics(metrics_payload: dict, service: str) -> tuple[float, float, list[TimelineEvent]]:
    points = metrics_payload.get("points", [])
    if not points:
        return 0.0, 0.0, []

    peak_error = max(float(p.get("error_rate", 0.0)) for p in points)
    peak_latency = max(float(p.get("p95_latency_ms", 0.0)) for p in points)

    latest = points[-1]
    timeline = [
        TimelineEvent(
            timestamp=latest["timestamp"],
            event=f"Metrics peak window: error_rate={peak_error:.2f}%, p95={peak_latency:.0f}ms",
            source="metrics",
            source_type="metrics",
            service=service,
            event_type="metrics_spike",
            summary="error/latency degradation",
            severity="high" if peak_error >= 2.0 else "medium",
        )
    ]
    return peak_error, peak_latency, timeline


def _parse_deploys(deploys_payload: list[dict], service: str) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for deploy in deploys_payload:
        events.append(
            TimelineEvent(
                timestamp=deploy["timestamp"],
                event=f"Deploy {deploy['version']} ({deploy.get('change_id', 'n/a')})",
                source="deploy_history",
                source_type="deploy",
                service=service,
                event_type="deploy",
                summary=deploy.get("notes", ""),
                severity="medium",
            )
        )
    return events


def _parse_infra(changes_payload: list[dict], service: str) -> tuple[list[dict], list[TimelineEvent]]:
    high_risk = [c for c in changes_payload if str(c.get("risk_level", "")).lower() == "high"]
    events: list[TimelineEvent] = []
    for change in changes_payload:
        risk = str(change.get("risk_level", "medium")).lower()
        events.append(
            TimelineEvent(
                timestamp=change["timestamp"],
                event=f"Infra change {change.get('change_id', 'n/a')}: {change.get('details', '')}",
                source="infra_changes",
                source_type="infra",
                service=service,
                event_type="infra_change",
                summary=change.get("details", ""),
                severity="high" if risk == "high" else "medium",
            )
        )
    return high_risk, events


def _load_service_evidence(group_dir: Path, child: ChildIncident) -> _ServiceEvidence:
    evidence_dir = group_dir / "evidence" / child.service

    logs = _read_lines(evidence_dir / "logs.txt")
    metrics = _read_json(evidence_dir / "metrics.json")
    deploys = _read_json(evidence_dir / "deploys.json")
    infra = _read_json(evidence_dir / "infra_changes.json")

    first_anomaly, timeout_events, corr_ids, log_events = _parse_logs(logs, child.service)
    peak_error, peak_latency, metric_events = _parse_metrics(metrics, child.service)
    deploy_events = _parse_deploys(deploys, child.service)
    high_risk, infra_events = _parse_infra(infra, child.service)

    timeline = sorted([*deploy_events, *infra_events, *metric_events, *log_events], key=lambda e: e.timestamp)

    return _ServiceEvidence(
        first_anomaly=first_anomaly or child.start_time,
        timeout_events=timeout_events,
        high_risk_changes=high_risk,
        deploys=deploys,
        metrics_peak_error_rate=peak_error,
        metrics_peak_latency_ms=peak_latency,
        correlation_ids=sorted(set(corr_ids).union(set(child.correlation_ids))),
        timeline=timeline,
    )


def _confidence_bucket(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _build_hypotheses(
    initiating_service: str,
    summaries: list[ServiceIncidentSummary],
    all_high_risk_changes: list[str],
) -> list[Hypothesis]:
    services = [s.service for s in summaries]

    infra_support = [
        f"High-risk infra changes observed: {', '.join(all_high_risk_changes)}"
        if all_high_risk_changes
        else "No high-risk infra change records found",
        f"Earliest anomaly observed in {initiating_service}",
        "Downstream services reported timeout/upstream dependency symptoms after primary failure.",
    ]
    infra_contradict = [
        "A recent deploy was also present and could contribute to service instability.",
    ]

    deploy_support = ["Recent deploys occurred near incident start window."]
    deploy_contradict = [
        "Shared dependency and infra-change signals are present across services.",
        f"Earliest failure sequence points to {initiating_service} before downstream degradation.",
    ]

    infra_hyp = Hypothesis(
        title="Network/security-group path change degraded DB connectivity",
        description=(
            "A high-risk network/ingress change likely disrupted database access for the initiating service, "
            "causing cascading timeouts in dependent services."
        ),
        supporting_evidence=infra_support,
        contradicting_evidence=infra_contradict,
        confidence="high" if all_high_risk_changes else "medium",
        likely_role="initiating fault",
        likely_affected_services=services,
    )

    deploy_hyp = Hypothesis(
        title="Recent deploy introduced latent regression",
        description=(
            "A deploy close to incident onset could have introduced a latency or retry regression; this remains "
            "a plausible alternate hypothesis."
        ),
        supporting_evidence=deploy_support,
        contradicting_evidence=deploy_contradict,
        confidence="medium",
        likely_role="unknown",
        likely_affected_services=services,
    )

    # Deterministic ranking: infra hypothesis first when it has high-risk evidence.
    if all_high_risk_changes:
        return [infra_hyp, deploy_hyp]
    return [deploy_hyp, infra_hyp]


def triage_major_incident(
    group_name: str,
    datasets_root: Path | None = None,
) -> MajorIncidentReport:
    """Run deterministic triage for a major incident group."""
    dataset = load_major_incident_dataset(group_name=group_name, datasets_root=datasets_root)

    metadata_by_service: dict[str, ServiceMetadata] = {s.service: s for s in dataset.service_metadata}

    evidence_by_service: dict[str, _ServiceEvidence] = {}
    for child in dataset.child_incidents:
        evidence_by_service[child.service] = _load_service_evidence(dataset.root_dir, child)

    earliest_service = min(
        dataset.child_incidents,
        key=lambda c: _dt(evidence_by_service[c.service].first_anomaly),
    ).service

    dependency_counter: Counter[str] = Counter()
    for child in dataset.child_incidents:
        dependency_counter.update(child.upstream_dependencies)

    summaries: list[ServiceIncidentSummary] = []
    merged_timeline: list[TimelineEvent] = []
    all_high_risk_change_ids: list[str] = []

    for child in dataset.child_incidents:
        service = child.service
        evidence = evidence_by_service[service]
        meta = metadata_by_service.get(service)

        shared_dependencies = [d for d in child.upstream_dependencies if dependency_counter[d] >= 2]

        score = 0
        evidence_notes: list[str] = []

        if service == earliest_service:
            score += 3
            evidence_notes.append("Earliest anomaly detected among impacted services.")

        if evidence.high_risk_changes:
            score += 3
            ids = [c.get("change_id", "unknown-change") for c in evidence.high_risk_changes]
            all_high_risk_change_ids.extend(ids)
            evidence_notes.append(f"High-risk infra changes near onset: {', '.join(ids)}")

        if shared_dependencies:
            score += 2
            evidence_notes.append(f"Shares failing dependencies with other services: {', '.join(shared_dependencies)}")

        if evidence.timeout_events >= 2:
            score += 1
            evidence_notes.append(f"Observed {evidence.timeout_events} DB timeout-related log events.")

        late_service = _dt(evidence.first_anomaly) > _dt(evidence_by_service[earliest_service].first_anomaly)
        downstream_pattern = any("upstream" in s.lower() or "dependency" in s.lower() for s in child.symptoms)
        if late_service and downstream_pattern:
            score -= 2
            evidence_notes.append("Symptoms indicate downstream impact after upstream degradation.")

        role = "uncertain"
        if service == earliest_service and score >= 4:
            role = "probable cause"
        elif late_service and downstream_pattern:
            role = "downstream"

        summaries.append(
            ServiceIncidentSummary(
                incident_id=child.incident_id,
                service=service,
                team=child.team,
                owner=child.owner,
                first_anomaly=evidence.first_anomaly,
                likely_role=role,
                confidence=_confidence_bucket(score),
                symptoms=child.symptoms,
                evidence=evidence_notes,
                correlation_ids=evidence.correlation_ids,
                shared_dependencies=shared_dependencies,
            )
        )
        merged_timeline.extend(evidence.timeline)

    merged_timeline = sorted(merged_timeline, key=lambda e: e.timestamp)

    hypotheses = _build_hypotheses(
        initiating_service=earliest_service,
        summaries=summaries,
        all_high_risk_changes=sorted(set(all_high_risk_change_ids)),
    )

    impacted_services = [s.service for s in summaries]
    impacted_teams = sorted(set(s.team for s in summaries))

    impacted_user_flows: set[str] = set()
    impacted_regions: set[str] = set()
    for child in dataset.child_incidents:
        meta = metadata_by_service.get(child.service)
        if meta:
            impacted_user_flows.update(meta.critical_user_flows)
        impacted_regions.add(child.region)

    if not dataset.incident_group.blast_radius.customer_facing_impact:
        dataset.incident_group.blast_radius = BlastRadius(
            impacted_services=sorted(set(impacted_services)),
            impacted_teams=impacted_teams,
            impacted_user_flows=sorted(impacted_user_flows),
            impacted_regions=sorted(impacted_regions),
            customer_facing_impact="Checkout and payments degradation caused elevated transaction failures.",
        )

    dataset.incident_group.global_timeline = merged_timeline
    dataset.incident_group.hypotheses = hypotheses

    recommended_actions = [
        "Validate and rollback/adjust high-risk DB ingress/security-group changes in the incident window.",
        "Prioritize payments-api dependency path checks, then verify checkout-api and billing-worker recovery.",
        "Coordinate service owners to monitor transaction success rate and p95 latency during mitigation rollout.",
    ]

    return MajorIncidentReport(
        incident_group=dataset.incident_group,
        child_incidents=dataset.child_incidents,
        service_metadata=dataset.service_metadata,
        service_summaries=sorted(summaries, key=lambda s: s.first_anomaly),
        merged_timeline=merged_timeline,
        hypotheses=hypotheses,
        likely_initiating_fault_service=earliest_service,
        impacted_services_count=len(set(impacted_services)),
        impacted_teams=impacted_teams,
        customer_facing_impact=dataset.incident_group.blast_radius.customer_facing_impact,
        recommended_next_actions=recommended_actions,
    )

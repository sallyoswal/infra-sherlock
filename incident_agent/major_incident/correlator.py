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
    ChangeEvent,
    ChildIncident,
    FailurePatternMatch,
    Hypothesis,
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


def _match_suspicious_changes(
    change_events: list[ChangeEvent],
    earliest_ts: str,
    initiating_service: str,
) -> list[ChangeEvent]:
    t0 = _dt(earliest_ts)
    candidates: list[tuple[int, ChangeEvent]] = []

    for change in change_events:
        proximity_minutes = abs(int((_dt(change.timestamp) - t0).total_seconds() // 60))
        if proximity_minutes > 20:
            continue

        score = 0
        if change.risk.lower() == "high":
            score += 4
        elif change.risk.lower() == "medium":
            score += 2

        if initiating_service in change.related_services:
            score += 3

        if change.resource_type in {"security_group", "route_table", "nacl", "dns"}:
            score += 3

        # Closer changes are more suspicious.
        score += max(0, 5 - proximity_minutes)

        if score > 0:
            candidates.append((score, change))

    candidates.sort(key=lambda item: (-item[0], item[1].timestamp))
    return [c for _, c in candidates]


def _infer_infrastructure_layer(top_change: ChangeEvent | None) -> str:
    if top_change is None:
        return "unknown"

    mapping = {
        "security_group": "network_boundary",
        "route_table": "network_boundary",
        "nacl": "network_boundary",
        "dns": "edge_routing",
        "alb": "load_balancer",
        "postgres": "database",
        "rds": "database",
        "redis": "cache",
        "service": "application",
    }
    return mapping.get(top_change.resource_type, "application")


def _infer_blast_radius_scope(children: list[ChildIncident]) -> str:
    regions = sorted(set(c.region for c in children))
    azs = sorted({az for c in children for az in c.availability_zones})

    if len(regions) == 1 and len(azs) <= 2:
        return "localized"
    if len(regions) == 1:
        return "regional"
    return "multi-region"


def _fastest_validation_step(top_change: ChangeEvent | None, layer: str) -> str:
    if top_change is None:
        return "Validate dependency health checks between initiating service and shared upstream dependencies."

    if top_change.resource_type == "security_group":
        return (
            f"Compare DB connection success rate and rejected connections before/after {top_change.change_id} "
            f"on {top_change.resource_name}."
        )
    if top_change.resource_type in {"route_table", "nacl", "dns"}:
        return (
            f"Run targeted connectivity probes for {top_change.resource_name} in {top_change.region} to confirm "
            f"routing/ACL behavior after {top_change.change_id}."
        )
    if top_change.source == "deploy":
        return (
            f"Canary rollback {top_change.change_id} and compare error rate + latency for 15 minutes."
        )

    return f"Validate the top suspicious {layer} change {top_change.change_id} with before/after metrics."


def _compute_pattern_signals(
    summaries: list[ServiceIncidentSummary],
    suspicious_changes: list[ChangeEvent],
    blast_scope: str,
    shared_corr: bool,
) -> dict[str, bool]:
    has_db_timeouts = any(any("timeout" in e.lower() for e in s.evidence) for s in summaries)
    has_downstream = any(s.likely_role == "downstream" for s in summaries)
    only_one_service_probable = sum(1 for s in summaries if s.likely_role == "probable cause") == 1

    return {
        "high_risk_network_change": any(
            c.risk.lower() == "high" and c.resource_type in {"security_group", "route_table", "nacl", "dns"}
            for c in suspicious_changes
        ),
        "db_timeout_spike": has_db_timeouts,
        "earliest_service_first": only_one_service_probable,
        "downstream_upstream_symptoms": has_downstream,
        "shared_correlation_id": shared_corr,
        "dependency_fanout": len(summaries) >= 3,
        "recent_deploy_near_onset": any(c.source == "deploy" for c in suspicious_changes),
        "single_service_isolated": len(summaries) == 1,
        "single_az_concentration": blast_scope == "localized",
        "bounded_blast_radius": blast_scope in {"localized", "regional"},
    }


def _match_failure_patterns(pattern_defs: list[dict], signals: dict[str, bool]) -> list[FailurePatternMatch]:
    matches: list[FailurePatternMatch] = []
    for pattern in pattern_defs:
        required = list(pattern.get("required_signals", []))
        supporting = [s for s in required if signals.get(s, False)]
        contradicting = [s for s in required if not signals.get(s, False)]

        ratio = len(supporting) / len(required) if required else 0.0
        if ratio >= 0.8:
            confidence = "high"
        elif ratio >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        matches.append(
            FailurePatternMatch(
                pattern_name=pattern["pattern_name"],
                description=pattern.get("description", ""),
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                confidence=confidence,
                recommended_validation=(
                    f"Validate signals for pattern {pattern['pattern_name']} by checking: "
                    f"{', '.join(required[:2]) if required else 'core telemetry'}"
                ),
            )
        )

    order = {"high": 0, "medium": 1, "low": 2}
    matches.sort(key=lambda m: (order[m.confidence], m.pattern_name))
    return matches


def _build_hypotheses(
    initiating_service: str,
    summaries: list[ServiceIncidentSummary],
    suspicious_changes: list[ChangeEvent],
) -> list[Hypothesis]:
    services = [s.service for s in summaries]
    high_risk_change_ids = [c.change_id for c in suspicious_changes if c.risk.lower() == "high"]

    infra_support = [
        f"High-risk infra changes near first anomaly: {', '.join(high_risk_change_ids)}"
        if high_risk_change_ids
        else "No high-risk infra changes near first anomaly.",
        f"Earliest anomaly observed in {initiating_service}",
        "Downstream services showed upstream timeout/dependency symptoms after primary failure.",
    ]
    infra_contradict = [
        "A recent deploy was also present and remains an alternate explanation.",
    ]

    deploy_support = [
        "A recent deploy occurred near incident onset and could explain a service-local regression.",
    ]
    deploy_contradict = [
        "Cross-service dependency impact and shared timing align better with infrastructure-layer disruption.",
    ]

    infra_hyp = Hypothesis(
        title="Network/security-group path change degraded DB connectivity",
        description=(
            "A high-risk network boundary change likely disrupted database access for the initiating service, "
            "causing timeout cascades in dependent services."
        ),
        supporting_evidence=infra_support,
        contradicting_evidence=infra_contradict,
        confidence="high" if high_risk_change_ids else "medium",
        likely_role="initiating fault",
        likely_affected_services=services,
    )

    deploy_hyp = Hypothesis(
        title="Recent deploy introduced latent regression",
        description="A deploy close to onset could have added latency/retry regression and amplified failures.",
        supporting_evidence=deploy_support,
        contradicting_evidence=deploy_contradict,
        confidence="medium",
        likely_role="unknown",
        likely_affected_services=services,
    )

    return [infra_hyp, deploy_hyp] if high_risk_change_ids else [deploy_hyp, infra_hyp]


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

    earliest_child = min(
        dataset.child_incidents,
        key=lambda c: _dt(evidence_by_service[c.service].first_anomaly),
    )
    earliest_service = earliest_child.service
    earliest_ts = evidence_by_service[earliest_service].first_anomaly

    dependency_counter: Counter[str] = Counter()
    for child in dataset.child_incidents:
        dependency_counter.update(child.upstream_dependencies)

    summaries: list[ServiceIncidentSummary] = []
    merged_timeline: list[TimelineEvent] = []

    for child in dataset.child_incidents:
        service = child.service
        evidence = evidence_by_service[service]

        shared_dependencies = [d for d in child.upstream_dependencies if dependency_counter[d] >= 2]

        score = 0
        evidence_notes: list[str] = []

        if service == earliest_service:
            score += 3
            evidence_notes.append("Earliest anomaly detected among impacted services.")

        if evidence.high_risk_changes:
            score += 2
            ids = [c.get("change_id", "unknown-change") for c in evidence.high_risk_changes]
            evidence_notes.append(f"Service-local high-risk infra changes near onset: {', '.join(ids)}")

        if shared_dependencies:
            score += 2
            evidence_notes.append(f"Shares failing dependencies with peers: {', '.join(shared_dependencies)}")

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

    suspicious_changes = _match_suspicious_changes(dataset.change_events, earliest_ts, earliest_service)
    top_change = suspicious_changes[0] if suspicious_changes else None

    layer = _infer_infrastructure_layer(top_change)
    blast_scope = _infer_blast_radius_scope(dataset.child_incidents)
    fault_domain = "infrastructure" if layer in {"network_boundary", "database", "edge_routing"} else "service"

    shared_corr_ids = set.intersection(*(set(s.correlation_ids) for s in summaries)) if summaries else set()
    signals = _compute_pattern_signals(
        summaries=summaries,
        suspicious_changes=suspicious_changes,
        blast_scope=blast_scope,
        shared_corr=bool(shared_corr_ids),
    )
    pattern_matches = _match_failure_patterns(dataset.failure_patterns, signals)

    hypotheses = _build_hypotheses(
        initiating_service=earliest_service,
        summaries=summaries,
        suspicious_changes=suspicious_changes,
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

    fastest_step = _fastest_validation_step(top_change, layer)
    downstream_services = [
        s.service for s in summaries if s.service != earliest_service and s.likely_role == "downstream"
    ]
    if downstream_services:
        action_two = (
            f"Prioritize {earliest_service} dependency path checks, then verify "
            f"{', '.join(downstream_services[:2])} recovery."
        )
    else:
        action_two = f"Prioritize {earliest_service} dependency path checks."

    recommended_actions = [
        fastest_step,
        action_two,
        "Coordinate service owners to monitor transaction success rate and p95 latency during mitigation rollout.",
    ]

    return MajorIncidentReport(
        incident_group=dataset.incident_group,
        child_incidents=dataset.child_incidents,
        service_metadata=dataset.service_metadata,
        service_summaries=sorted(summaries, key=lambda s: s.first_anomaly),
        merged_timeline=merged_timeline,
        hypotheses=hypotheses,
        failure_patterns=pattern_matches,
        likely_initiating_fault_service=earliest_service,
        likely_fault_domain=fault_domain,
        likely_infrastructure_layer=layer,
        suspicious_change_ids=[c.change_id for c in suspicious_changes[:3]],
        blast_radius_scope=blast_scope,
        fastest_validation_step=fastest_step,
        impacted_services_count=len(set(impacted_services)),
        impacted_teams=impacted_teams,
        customer_facing_impact=dataset.incident_group.blast_radius.customer_facing_impact,
        recommended_next_actions=recommended_actions,
    )

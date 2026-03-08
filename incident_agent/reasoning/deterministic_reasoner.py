"""Deterministic incident reasoner using explicit heuristics."""

from __future__ import annotations

from incident_agent.models import (
    DeployAnalysis,
    IncidentMetadata,
    IncidentReport,
    InfraAnalysis,
    LogAnalysis,
    MetricsAnalysis,
    TimelineEvent,
)


def _score_confidence(
    logs: LogAnalysis,
    metrics: MetricsAnalysis,
    deploys: DeployAnalysis,
    infra: InfraAnalysis,
) -> float:
    score = 0.0

    if logs.db_timeout_events >= 3:
        score += 0.35
    if metrics.error_rate_rising:
        score += 0.2
    if metrics.latency_rising:
        score += 0.2
    if deploys.latest_deploy is not None:
        score += 0.05
    if infra.high_risk_changes:
        score += 0.2

    return min(score, 0.99)


def _infer_root_cause(
    logs: LogAnalysis,
    metrics: MetricsAnalysis,
    deploys: DeployAnalysis,
    infra: InfraAnalysis,
) -> str:
    """Infer likely root cause from available signals."""
    if infra.high_risk_changes and logs.db_timeout_events >= 3 and infra.latest_change:
        change = infra.latest_change
        return (
            f"High-risk {change.change_type} to {change.component} at {change.timestamp} "
            f"likely caused {logs.db_timeout_events} DB timeout events and rising latency."
        )
    if deploys.latest_deploy and metrics.error_rate_rising:
        deploy = deploys.latest_deploy
        return (
            f"Deploy {deploy.version} to {deploy.service} at {deploy.timestamp} "
            "correlated with rising error rate."
        )
    if metrics.latency_rising and metrics.error_rate_rising:
        return (
            "Rising error rate and p95 latency with no clear infra or deploy trigger. "
            "Investigate DB and upstream dependencies."
        )
    return "Root cause unclear. Insufficient signal correlation. Manual investigation required."


def build_report(
    metadata: IncidentMetadata,
    logs: LogAnalysis,
    metrics: MetricsAnalysis,
    deploys: DeployAnalysis,
    infra: InfraAnalysis,
) -> IncidentReport:
    """Produce a structured root-cause report from tool outputs."""
    confidence = _score_confidence(logs=logs, metrics=metrics, deploys=deploys, infra=infra)

    likely_root_cause = _infer_root_cause(logs=logs, metrics=metrics, deploys=deploys, infra=infra)

    evidence = [
        f"Observed {logs.db_timeout_events} database timeout log events.",
        f"Error rate increased to {metrics.peak_error_rate:.2f}%.",
        f"p95 latency increased to {metrics.peak_p95_latency_ms:.0f}ms.",
    ]

    if deploys.latest_deploy:
        evidence.append(
            f"Recent deploy {deploys.latest_deploy.version} at {deploys.latest_deploy.timestamp}."
        )
    if infra.latest_change:
        evidence.append(
            f"Recent infra change ({infra.latest_change.risk_level} risk): "
            f"{infra.latest_change.component} {infra.latest_change.change_type} at {infra.latest_change.timestamp}."
        )

    timeline: list[TimelineEvent] = []

    for deploy in deploys.records:
        timeline.append(
            TimelineEvent(
                timestamp=deploy.timestamp,
                event=f"Deploy {deploy.version} to {deploy.service}",
                source="deploy_history",
            )
        )

    for change in infra.changes:
        timeline.append(
            TimelineEvent(
                timestamp=change.timestamp,
                event=f"Infra change ({change.risk_level}): {change.details}",
                source="infra_changes",
            )
        )

    for log_event in logs.timeline_events:
        timeline.append(
            TimelineEvent(
                timestamp=log_event.timestamp,
                event=f"{log_event.level} log: {log_event.message}",
                source="logs",
            )
        )

    timeline = sorted(timeline, key=lambda e: e.timestamp)

    remediation = [
        "Rollback or adjust the recent high-risk network/security change affecting DB connectivity.",
        "Temporarily increase DB client timeout and add bounded retry with jitter in the payments service.",
        "Re-run canary health checks and monitor error/latency for at least 30 minutes after mitigation.",
    ]

    next_steps = [
        "Validate database connection success rate by source subnet and security group before/after change.",
        "Compare slow query and connection pool stats during incident window.",
        "Add synthetic transaction checks for payments->DB path to catch regressions earlier.",
    ]

    return IncidentReport(
        incident_name=metadata.incident_name,
        incident_title=metadata.title,
        service_name=metadata.service_name,
        likely_root_cause=likely_root_cause,
        confidence=confidence,
        key_evidence=evidence,
        timeline=timeline,
        suggested_remediation=remediation,
        next_investigative_steps=next_steps,
    )

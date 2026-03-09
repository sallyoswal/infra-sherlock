from __future__ import annotations

import sys
from pathlib import Path

import pytest
from incident_agent.models import IncidentReport, TimelineEvent

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def configure_fake_llm(monkeypatch) -> None:
    """Run tests in AI-only mode without making real API calls."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    from incident_agent import agent

    def _fake_llm_report(*, metadata, logs, metrics, deploys, infra):
        key_evidence = [
            f"Observed {logs.db_timeout_events} database timeout log events.",
            f"Error rate rising signal: {metrics.error_rate_rising}.",
            f"Latency rising signal: {metrics.latency_rising}.",
        ]
        if infra.latest_change:
            key_evidence.append(
                f"Recent infra change ({infra.latest_change.risk_level} risk): "
                f"{infra.latest_change.component} {infra.latest_change.change_type} at {infra.latest_change.timestamp}."
            )
        if deploys.latest_deploy:
            key_evidence.append(
                f"Recent deploy {deploys.latest_deploy.version} at {deploys.latest_deploy.timestamp}."
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
        timeline.sort(key=lambda item: item.timestamp)

        likely_root_cause = "Root cause unclear. Insufficient signal correlation. Manual investigation required."
        if infra.high_risk_changes and logs.db_timeout_events >= 3 and infra.latest_change:
            likely_root_cause = (
                f"High-risk {infra.latest_change.change_type} to {infra.latest_change.component} at "
                f"{infra.latest_change.timestamp} likely caused {logs.db_timeout_events} DB timeout events."
            )
        elif deploys.latest_deploy and metrics.error_rate_rising:
            likely_root_cause = (
                f"Deploy {deploys.latest_deploy.version} to {deploys.latest_deploy.service} at "
                f"{deploys.latest_deploy.timestamp} correlated with rising error rate."
            )

        confidence = 0.55
        if logs.db_timeout_events >= 3:
            confidence += 0.2
        if metrics.error_rate_rising:
            confidence += 0.1
        if metrics.latency_rising:
            confidence += 0.1
        if infra.high_risk_changes:
            confidence += 0.1
        confidence = min(confidence, 0.99)

        return IncidentReport(
            incident_name=metadata.incident_name,
            incident_title=metadata.title,
            service_name=metadata.service_name,
            likely_root_cause=likely_root_cause,
            confidence=confidence,
            key_evidence=key_evidence,
            timeline=timeline,
            suggested_remediation=[
                "Rollback or adjust the recent high-risk network/security change affecting DB connectivity.",
                f"Temporarily increase DB client timeout and add bounded retry with jitter in the {metadata.service_name} service.",
                "Re-run canary health checks and monitor error/latency for at least 30 minutes after mitigation.",
            ],
            next_investigative_steps=[
                "Validate database connection success rate by source subnet and security group before/after change.",
                "Compare slow query and connection pool stats during incident window.",
                f"Add synthetic transaction checks for {metadata.service_name}->DB path to catch regressions earlier.",
            ],
        )

    monkeypatch.setattr(agent, "build_report_with_llm", _fake_llm_report)

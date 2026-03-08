"""Structured models for incident analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IncidentMetadata:
    """Metadata describing the incident scenario."""

    incident_name: str
    title: str
    service_name: str


@dataclass
class LogAnalysis:
    """Summary extracted from log events."""

    total_events: int
    error_events: int
    db_timeout_events: int
    first_timestamp: str | None
    last_timestamp: str | None
    sample_timeout_messages: list[str] = field(default_factory=list)


@dataclass
class MetricPoint:
    """Single metric snapshot for a service."""

    timestamp: str
    error_rate: float
    p95_latency_ms: float


@dataclass
class MetricsAnalysis:
    """Summary extracted from metric time series."""

    points: list[MetricPoint]
    error_rate_rising: bool
    latency_rising: bool
    peak_error_rate: float
    peak_p95_latency_ms: float


@dataclass
class DeployRecord:
    """Single deploy event."""

    timestamp: str
    version: str
    service: str
    notes: str


@dataclass
class DeployAnalysis:
    """Summary extracted from deploy history."""

    records: list[DeployRecord]
    latest_deploy: DeployRecord | None


@dataclass
class InfraChange:
    """Single infrastructure change event."""

    timestamp: str
    component: str
    change_type: str
    risk_level: str
    details: str


@dataclass
class InfraAnalysis:
    """Summary extracted from infrastructure change history."""

    changes: list[InfraChange]
    latest_change: InfraChange | None
    high_risk_changes: list[InfraChange]


@dataclass
class TimelineEvent:
    """Chronological event included in the final report."""

    timestamp: str
    event: str
    source: str


@dataclass
class IncidentReport:
    """Final deterministic report for an incident."""

    incident_name: str
    incident_title: str
    service_name: str
    likely_root_cause: str
    confidence: float
    key_evidence: list[str]
    timeline: list[TimelineEvent]
    suggested_remediation: list[str]
    next_investigative_steps: list[str]

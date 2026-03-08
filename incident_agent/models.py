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
class LogEvent:
    """Single log event retained for timeline reconstruction."""

    timestamp: str
    level: str
    message: str


@dataclass
class LogAnalysis:
    """Summary extracted from log events."""

    total_events: int
    error_events: int
    db_timeout_events: int
    first_timestamp: str | None
    last_timestamp: str | None
    sample_timeout_messages: list[str] = field(default_factory=list)
    timeline_events: list[LogEvent] = field(default_factory=list)


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
    source_type: str = ""
    service: str = ""
    event_type: str = ""
    summary: str = ""
    severity: str = ""


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


@dataclass
class ServiceMetadata:
    """Ownership and dependency metadata for a service."""

    service: str
    team: str
    owner: str
    tier: str
    dependencies: list[str]
    critical_user_flows: list[str]


@dataclass
class ChildIncident:
    """Service-scoped incident record used in a major incident group."""

    incident_id: str
    service: str
    team: str
    owner: str
    start_time: str
    symptoms: list[str]
    correlation_ids: list[str]
    upstream_dependencies: list[str]
    downstream_dependencies: list[str]
    related_change_ids: list[str]
    report_summary: str = ""
    environment: str = "prod"
    region: str = "us-east-1"


@dataclass
class BlastRadius:
    """Impacted surface area for a major incident."""

    impacted_services: list[str]
    impacted_teams: list[str]
    impacted_user_flows: list[str]
    impacted_regions: list[str]
    customer_facing_impact: str


@dataclass
class Hypothesis:
    """Ranked explanation for major-incident correlation output."""

    title: str
    description: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    confidence: str
    likely_role: str
    likely_affected_services: list[str] = field(default_factory=list)


@dataclass
class IncidentGroup:
    """Parent incident group spanning multiple child incidents/services."""

    group_id: str
    title: str
    status: str
    severity: str
    start_time: str
    end_time: str | None
    commander: str
    summary: str
    child_incident_ids: list[str]
    suspected_root_services: list[str]
    blast_radius: BlastRadius
    global_timeline: list[TimelineEvent] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)


@dataclass
class ServiceIncidentSummary:
    """Normalized per-service view used during major-incident triage."""

    incident_id: str
    service: str
    team: str
    owner: str
    first_anomaly: str
    likely_role: str
    confidence: str
    symptoms: list[str]
    evidence: list[str]
    correlation_ids: list[str]
    shared_dependencies: list[str]


@dataclass
class MajorIncidentReport:
    """Deterministic major-incident triage output."""

    incident_group: IncidentGroup
    child_incidents: list[ChildIncident]
    service_metadata: list[ServiceMetadata]
    service_summaries: list[ServiceIncidentSummary]
    merged_timeline: list[TimelineEvent]
    hypotheses: list[Hypothesis]
    likely_initiating_fault_service: str
    impacted_services_count: int
    impacted_teams: list[str]
    customer_facing_impact: str
    recommended_next_actions: list[str]

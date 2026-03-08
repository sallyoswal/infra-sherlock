"""Load local major-incident datasets from structured files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from incident_agent.loader import IncidentDataError, incident_dir, load_json
from incident_agent.models import (
    BlastRadius,
    ChangeEvent,
    ChildIncident,
    IncidentGroup,
    InfrastructureComponent,
    ServiceMetadata,
)


@dataclass
class MajorIncidentDataset:
    """In-memory dataset for major-incident correlation."""

    root_dir: Path
    incident_group: IncidentGroup
    service_metadata: list[ServiceMetadata]
    child_incidents: list[ChildIncident]
    infrastructure_components: list[InfrastructureComponent]
    change_events: list[ChangeEvent]
    failure_patterns: list[dict]


def _parse_blast_radius(payload: dict) -> BlastRadius:
    return BlastRadius(
        impacted_services=list(payload.get("impacted_services", [])),
        impacted_teams=list(payload.get("impacted_teams", [])),
        impacted_user_flows=list(payload.get("impacted_user_flows", [])),
        impacted_regions=list(payload.get("impacted_regions", [])),
        customer_facing_impact=str(payload.get("customer_facing_impact", "")),
    )


def _parse_group(payload: dict) -> IncidentGroup:
    blast_payload = payload.get("blast_radius", {})
    return IncidentGroup(
        group_id=payload["group_id"],
        title=payload["title"],
        status=payload["status"],
        severity=payload["severity"],
        start_time=payload["start_time"],
        end_time=payload.get("end_time"),
        commander=payload["commander"],
        summary=payload["summary"],
        child_incident_ids=list(payload.get("child_incident_ids", [])),
        suspected_root_services=list(payload.get("suspected_root_services", [])),
        blast_radius=_parse_blast_radius(blast_payload),
    )


def _parse_services(payload: list[dict]) -> list[ServiceMetadata]:
    services: list[ServiceMetadata] = []
    for item in payload:
        services.append(
            ServiceMetadata(
                service=item["service"],
                team=item["team"],
                owner=item["owner"],
                tier=item["tier"],
                dependencies=list(item.get("dependencies", [])),
                critical_user_flows=list(item.get("critical_user_flows", [])),
                region=str(item.get("region", "us-east-1")),
                availability_zones=list(item.get("availability_zones", [])),
                infrastructure_components=list(item.get("infrastructure_components", [])),
            )
        )
    return services


def _parse_child(payload: dict) -> ChildIncident:
    return ChildIncident(
        incident_id=payload["incident_id"],
        service=payload["service"],
        team=payload["team"],
        owner=payload["owner"],
        start_time=payload["start_time"],
        symptoms=list(payload.get("symptoms", [])),
        correlation_ids=list(payload.get("correlation_ids", [])),
        upstream_dependencies=list(payload.get("upstream_dependencies", [])),
        downstream_dependencies=list(payload.get("downstream_dependencies", [])),
        related_change_ids=list(payload.get("related_change_ids", [])),
        report_summary=str(payload.get("report_summary", "")),
        environment=str(payload.get("environment", "prod")),
        region=str(payload.get("region", "us-east-1")),
        availability_zones=list(payload.get("availability_zones", [])),
    )


def _parse_infrastructure(payload: list[dict]) -> list[InfrastructureComponent]:
    components: list[InfrastructureComponent] = []
    for item in payload:
        components.append(
            InfrastructureComponent(
                component_id=item["component_id"],
                type=item["type"],
                region=item["region"],
                availability_zones=list(item.get("availability_zones", [])),
                owner_team=item["owner_team"],
                connected_services=list(item.get("connected_services", [])),
            )
        )
    return components


def _parse_change_events(payload: list[dict]) -> list[ChangeEvent]:
    events: list[ChangeEvent] = []
    for item in payload:
        events.append(
            ChangeEvent(
                change_id=item["change_id"],
                timestamp=item["timestamp"],
                source=item["source"],
                resource_type=item["resource_type"],
                resource_name=item["resource_name"],
                operation=item["operation"],
                risk=item["risk"],
                related_services=list(item.get("related_services", [])),
                region=item.get("region", "us-east-1"),
                availability_zone=item.get("availability_zone"),
            )
        )
    return events


def load_major_incident_dataset(
    group_name: str,
    datasets_root: Path | None = None,
) -> MajorIncidentDataset:
    """Load a major-incident dataset folder into typed models."""
    if datasets_root is None:
        datasets_root = Path(__file__).resolve().parents[2] / "datasets" / "major_incidents"

    group_dir = incident_dir(datasets_root, group_name)

    group_payload = load_json(group_dir / "incident_group.json")
    service_payload = load_json(group_dir / "services.json")
    infra_payload = load_json(group_dir / "infrastructure.json")
    changes_payload = load_json(group_dir / "change_events.json")
    pattern_payload = load_json(group_dir / "failure_patterns.json")

    child_dir = group_dir / "child_incidents"
    if not child_dir.exists() or not child_dir.is_dir():
        raise IncidentDataError(f"Missing child_incidents directory in {group_dir}")

    child_incidents: list[ChildIncident] = []
    for path in sorted(child_dir.glob("*.json")):
        child_incidents.append(_parse_child(load_json(path)))

    incident_group = _parse_group(group_payload)
    services = _parse_services(service_payload)
    infrastructure = _parse_infrastructure(infra_payload)
    change_events = _parse_change_events(changes_payload)

    if not child_incidents:
        raise IncidentDataError(f"No child incident files found in {child_dir}")

    return MajorIncidentDataset(
        root_dir=group_dir,
        incident_group=incident_group,
        service_metadata=services,
        child_incidents=child_incidents,
        infrastructure_components=infrastructure,
        change_events=change_events,
        failure_patterns=list(pattern_payload),
    )

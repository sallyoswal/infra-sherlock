from __future__ import annotations

from incident_agent.major_incident.correlator import triage_major_incident


def test_initiating_fault_vs_downstream_classification() -> None:
    report = triage_major_incident("payments_sev1_march_2026")
    by_service = {s.service: s for s in report.service_summaries}

    assert report.likely_initiating_fault_service == "payments-api"
    assert by_service["payments-api"].likely_role in {"probable cause", "uncertain"}
    assert by_service["checkout-api"].likely_role == "downstream"


def test_hypothesis_ranking_and_confidence_bucket() -> None:
    report = triage_major_incident("payments_sev1_march_2026")
    assert len(report.hypotheses) >= 2
    assert report.hypotheses[0].confidence in {"high", "medium", "low"}
    assert "network" in report.hypotheses[0].title.lower() or "security" in report.hypotheses[0].title.lower()


def test_blast_radius_inference_and_timeline_ordering() -> None:
    report = triage_major_incident("payments_sev1_march_2026")
    blast = report.incident_group.blast_radius

    assert "payments-api" in blast.impacted_services
    assert "checkout-platform" in blast.impacted_teams
    assert "checkout" in blast.impacted_user_flows

    ts = [e.timestamp for e in report.merged_timeline]
    assert ts == sorted(ts)


def test_infrastructure_change_attribution_and_fault_domain() -> None:
    report = triage_major_incident("payments_sev1_march_2026")

    assert "chg-sg-773" in report.suspicious_change_ids
    assert report.likely_fault_domain == "infrastructure"
    assert report.likely_infrastructure_layer in {"network_boundary", "database", "edge_routing"}


def test_pattern_matching_and_validation_step() -> None:
    report = triage_major_incident("payments_sev1_march_2026")
    assert len(report.failure_patterns) >= 1
    top = report.failure_patterns[0]
    assert top.confidence in {"high", "medium", "low"}
    assert "Validate" in report.fastest_validation_step or "Compare" in report.fastest_validation_step


def test_region_az_scope_reasoning() -> None:
    report = triage_major_incident("payments_sev1_march_2026")
    assert report.blast_radius_scope in {"localized", "regional", "multi-region"}
    assert report.blast_radius_scope == "localized"

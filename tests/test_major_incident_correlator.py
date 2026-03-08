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

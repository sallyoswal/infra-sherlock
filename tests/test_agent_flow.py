from incident_agent.agent import investigate_incident


def test_end_to_end_investigation_flow() -> None:
    report = investigate_incident("payments_db_timeout")

    assert report.service_name == "payments-api"
    assert report.incident_name == "payments_db_timeout"
    assert len(report.key_evidence) >= 4
    assert len(report.suggested_remediation) >= 3

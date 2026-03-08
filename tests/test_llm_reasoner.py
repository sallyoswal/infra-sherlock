from __future__ import annotations

import pytest

from incident_agent.models import IncidentMetadata
from incident_agent.reasoning.llm_reasoner import LLMReasonerError, validate_and_build_report


def test_validate_and_build_report_success() -> None:
    metadata = IncidentMetadata(
        incident_name="payments_db_timeout",
        title="Payments API timeout spike after network policy change",
        service_name="payments-api",
    )
    payload = {
        "likely_root_cause": "db network path issue",
        "confidence": 0.82,
        "key_evidence": ["timeouts", "latency spike"],
        "timeline": [
            {
                "timestamp": "2026-03-06T10:00:00Z",
                "event": "error spike",
                "source": "metrics",
            }
        ],
        "suggested_remediation": ["rollback change"],
        "next_investigative_steps": ["check connection stats"],
    }

    report = validate_and_build_report(payload=payload, metadata=metadata)
    assert report.confidence == 0.82
    assert report.timeline[0].source == "metrics"


def test_validate_and_build_report_rejects_missing_keys() -> None:
    metadata = IncidentMetadata(
        incident_name="payments_db_timeout",
        title="Payments API timeout spike after network policy change",
        service_name="payments-api",
    )

    with pytest.raises(LLMReasonerError):
        validate_and_build_report(payload={"confidence": 0.7}, metadata=metadata)

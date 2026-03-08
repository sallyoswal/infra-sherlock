from __future__ import annotations

from incident_agent.major_incident.loader import load_major_incident_dataset


def test_load_major_incident_dataset() -> None:
    ds = load_major_incident_dataset("payments_sev1_march_2026")
    assert ds.incident_group.group_id == "payments-sev1-2026-03-06"
    assert len(ds.child_incidents) == 3
    assert any(s.service == "payments-api" for s in ds.service_metadata)

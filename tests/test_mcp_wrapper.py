from __future__ import annotations

import pytest

from incident_agent.mcp.wrapper import (
    get_investigate_tool_spec,
    investigate_incident_tool,
)


def test_get_investigate_tool_spec_shape() -> None:
    spec = get_investigate_tool_spec()
    assert spec["name"] == "investigate_incident"
    assert "input_schema" in spec
    assert "incident_name" in spec["input_schema"]["properties"]


def test_investigate_incident_tool_returns_structured_report() -> None:
    result = investigate_incident_tool("payments_db_timeout")
    assert result["incident_name"] == "payments_db_timeout"
    assert isinstance(result["timeline"], list)
    assert len(result["timeline"]) >= 1
    first_event = result["timeline"][0]
    assert {"timestamp", "event", "source"}.issubset(first_event.keys())


def test_investigate_incident_tool_rejects_empty_incident_name() -> None:
    with pytest.raises(ValueError):
        investigate_incident_tool("   ")

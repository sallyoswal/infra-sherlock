from __future__ import annotations

from incident_agent.mcp.server import _extract_remediation, _extract_timeline, create_mcp_app


def test_extract_timeline_filters_non_dict_entries() -> None:
    payload = {"timeline": [{"timestamp": "t1", "event": "e1", "source": "s1"}, "bad"]}
    result = _extract_timeline(payload)
    assert len(result) == 1
    assert result[0]["event"] == "e1"


def test_extract_remediation_normalizes_strings() -> None:
    payload = {"suggested_remediation": ["step1", 2]}
    result = _extract_remediation(payload)
    assert result == ["step1", "2"]


def test_create_mcp_app_or_clear_error() -> None:
    try:
        app = create_mcp_app()
        assert hasattr(app, "run")
    except RuntimeError as exc:
        assert "MCP SDK" in str(exc)

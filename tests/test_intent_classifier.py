from __future__ import annotations

from cli.intent_classifier import classify_user_input


def test_maps_what_happened_to_summary() -> None:
    result = classify_user_input("what happened")
    assert result.intent == "summary"


def test_maps_why_to_root_cause() -> None:
    result = classify_user_input("why?")
    assert result.intent == "root-cause"


def test_maps_timeline_keyword() -> None:
    result = classify_user_input("timeline")
    assert result.intent == "timeline"


def test_maps_how_to_fix_to_remediation() -> None:
    result = classify_user_input("how to fix this")
    assert result.intent == "remediation"


def test_maps_why_do_we_think_to_evidence() -> None:
    result = classify_user_input("why do we think it's network?")
    assert result.intent == "evidence"


def test_short_followup_uses_last_intent() -> None:
    result = classify_user_input("details", last_intent="evidence")
    assert result.intent == "evidence"
    assert result.detailed is True

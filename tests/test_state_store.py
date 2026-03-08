from __future__ import annotations

import json
from pathlib import Path

from incident_agent.notifications.state_store import NotificationStateStore


def test_state_store_mark_and_has_sent(tmp_path: Path) -> None:
    path = tmp_path / "alerts.json"
    store = NotificationStateStore(path)

    assert store.has_sent("inc-1", "abc") is False
    store.mark_sent("inc-1", "abc")
    assert store.has_sent("inc-1", "abc") is True
    assert store.has_sent("inc-1", "def") is False


def test_state_store_ttl_prunes_expired_entries(monkeypatch, tmp_path: Path) -> None:
    now = {"value": 1_700_000_000}
    monkeypatch.setattr(
        "incident_agent.notifications.state_store.time.time",
        lambda: float(now["value"]),
    )

    path = tmp_path / "alerts.json"
    store = NotificationStateStore(path, ttl_seconds=10)
    store.mark_sent("inc-1", "abc")
    assert store.has_sent("inc-1", "abc") is True

    now["value"] += 11
    assert store.has_sent("inc-1", "abc") is False


def test_state_store_reads_legacy_string_format(tmp_path: Path) -> None:
    path = tmp_path / "alerts.json"
    path.write_text(json.dumps({"inc-1": "abc"}), encoding="utf-8")
    store = NotificationStateStore(path)

    assert store.has_sent("inc-1", "abc") is True


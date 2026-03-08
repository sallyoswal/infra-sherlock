"""Simple local state store for notification dedupe."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time


class NotificationStateStore:
    """Persists hashes of already-sent alerts to avoid spam."""

    def __init__(self, path: Path, ttl_seconds: int = 24 * 60 * 60) -> None:
        self.path = path
        self.ttl_seconds = max(ttl_seconds, 0)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                normalized: dict[str, dict[str, object]] = {}
                now = int(time.time())
                for key, value in data.items():
                    incident_key = str(key)
                    if isinstance(value, str):
                        normalized[incident_key] = {
                            "fingerprint": value,
                            "sent_at": now,
                        }
                        continue
                    if isinstance(value, dict):
                        fingerprint = str(value.get("fingerprint", "")).strip()
                        sent_at = int(value.get("sent_at", now))
                        if fingerprint:
                            normalized[incident_key] = {
                                "fingerprint": fingerprint,
                                "sent_at": sent_at,
                            }
                return normalized
        except json.JSONDecodeError:
            return {}
        return {}

    def _write(self, data: dict[str, dict[str, object]]) -> None:
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp_path, self.path)

    def _prune_expired(self, data: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
        if self.ttl_seconds == 0:
            return {}
        now = int(time.time())
        kept: dict[str, dict[str, object]] = {}
        for incident_key, entry in data.items():
            sent_at = int(entry.get("sent_at", now))
            if now - sent_at <= self.ttl_seconds:
                kept[incident_key] = entry
        return kept

    def has_sent(self, incident_key: str, fingerprint: str) -> bool:
        data = self._prune_expired(self._read())
        return str(data.get(incident_key, {}).get("fingerprint", "")) == fingerprint

    def mark_sent(self, incident_key: str, fingerprint: str) -> None:
        data = self._prune_expired(self._read())
        data[incident_key] = {
            "fingerprint": fingerprint,
            "sent_at": int(time.time()),
        }
        self._write(data)

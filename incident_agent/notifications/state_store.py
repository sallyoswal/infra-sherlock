"""Simple local state store for notification dedupe."""

from __future__ import annotations

import json
from pathlib import Path


class NotificationStateStore:
    """Persists hashes of already-sent alerts to avoid spam."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            return {}
        return {}

    def _write(self, data: dict[str, str]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def has_sent(self, incident_key: str, fingerprint: str) -> bool:
        data = self._read()
        return data.get(incident_key) == fingerprint

    def mark_sent(self, incident_key: str, fingerprint: str) -> None:
        data = self._read()
        data[incident_key] = fingerprint
        self._write(data)

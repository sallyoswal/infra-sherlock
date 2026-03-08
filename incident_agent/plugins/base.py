"""Plugin contracts for optional cloud collectors and notifiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from incident_agent.models import TimelineEvent


@dataclass
class PluginEvidence:
    """Normalized evidence returned by a collector plugin."""

    key_evidence: list[str] = field(default_factory=list)
    timeline_events: list[TimelineEvent] = field(default_factory=list)


@dataclass
class IncidentContext:
    """Shared context passed to plugins."""

    incident_name: str
    service_name: str
    incident_dir: Path


class EvidencePlugin(Protocol):
    """Collector plugin interface."""

    name: str

    def healthcheck(self) -> tuple[bool, str]:
        """Return status and human-readable detail."""

    def collect(self, context: IncidentContext) -> PluginEvidence:
        """Collect evidence for the incident."""


class NotifierPlugin(Protocol):
    """Notification plugin interface."""

    name: str

    def healthcheck(self) -> tuple[bool, str]:
        """Return status and human-readable detail."""

    def notify(self, payload: dict[str, object]) -> tuple[bool, str]:
        """Send a notification payload and return status."""

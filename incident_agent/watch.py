"""Watch loop for detect->diagnose->notify workflow."""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from incident_agent.agent import investigate_incident
from incident_agent.loader import IncidentDataError
from incident_agent.models import IncidentReport
from incident_agent.reasoning.llm_reasoner import LLMReasonerError

_shutdown = False


def _handle_signal(signum: int, _frame: object) -> None:
    """Mark loop for shutdown on SIGTERM/SIGINT."""
    del signum
    global _shutdown
    _shutdown = True


@dataclass
class WatchResult:
    """Single watch iteration result."""

    incident_name: str
    report: IncidentReport | None
    error: str | None = None


def run_watch_iteration(
    incident_name: str,
    datasets_root: Path,
    plugin_config_path: Path | None = None,
    routing_config_path: Path | None = None,
    state_path: Path | None = None,
    investigation_mode: Literal["local", "cloud"] = "local",
    service_name: str | None = None,
    incident_title: str | None = None,
) -> WatchResult:
    """Run one incident watch iteration and send notifications if configured."""
    try:
        report = investigate_incident(
            incident_name=incident_name,
            datasets_root=datasets_root,
            plugin_config_path=plugin_config_path,
            routing_config_path=routing_config_path,
            notify=True,
            state_path=state_path,
            investigation_mode=investigation_mode,
            service_name=service_name,
            incident_title=incident_title,
        )
        return WatchResult(incident_name=incident_name, report=report)
    except (IncidentDataError, LLMReasonerError) as exc:
        return WatchResult(incident_name=incident_name, report=None, error=str(exc))


def run_watch_loop(
    incidents: list[str],
    datasets_root: Path,
    interval_seconds: int = 60,
    once: bool = False,
    plugin_config_path: Path | None = None,
    routing_config_path: Path | None = None,
    state_path: Path | None = None,
    investigation_mode: Literal["local", "cloud"] = "local",
    service_name: str | None = None,
    incident_title: str | None = None,
) -> list[WatchResult]:
    """Run watch loop for one or more incidents."""
    global _shutdown
    _shutdown = False
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    results: list[WatchResult] = []
    while not _shutdown:
        for incident_name in incidents:
            if _shutdown:
                break
            result = run_watch_iteration(
                incident_name=incident_name,
                datasets_root=datasets_root,
                plugin_config_path=plugin_config_path,
                routing_config_path=routing_config_path,
                state_path=state_path,
                investigation_mode=investigation_mode,
                service_name=service_name,
                incident_title=incident_title,
            )
            results.append(result)
        if once or _shutdown:
            return results
        time.sleep(interval_seconds)

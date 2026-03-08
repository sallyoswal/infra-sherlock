"""Watch loop for detect->diagnose->notify workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from incident_agent.agent import investigate_incident
from incident_agent.loader import IncidentDataError
from incident_agent.models import IncidentReport
from incident_agent.reasoning.llm_reasoner import LLMReasonerError


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
) -> WatchResult:
    """Run one incident watch iteration and send notifications if configured."""
    try:
        report = investigate_incident(
            incident_name=incident_name,
            datasets_root=datasets_root,
            prefer_llm=True,
            plugin_config_path=plugin_config_path,
            routing_config_path=routing_config_path,
            notify=True,
            state_path=state_path,
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
) -> list[WatchResult]:
    """Run watch loop for one or more incidents."""
    results: list[WatchResult] = []
    while True:
        for incident_name in incidents:
            result = run_watch_iteration(
                incident_name=incident_name,
                datasets_root=datasets_root,
                plugin_config_path=plugin_config_path,
                routing_config_path=routing_config_path,
                state_path=state_path,
            )
            results.append(result)
        if once:
            return results
        time.sleep(interval_seconds)

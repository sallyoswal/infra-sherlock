"""Incident investigation orchestrator."""

from __future__ import annotations

from pathlib import Path

from incident_agent.loader import incident_dir, load_json
from incident_agent.llm_provider import has_llm_credentials
from incident_agent.models import IncidentMetadata, IncidentReport
from incident_agent.reasoning.deterministic_reasoner import build_report as build_deterministic_report
from incident_agent.reasoning.llm_reasoner import LLMReasonerError, build_report_with_llm
from incident_agent.tools.deploy_tool import analyze_deploys
from incident_agent.tools.infra_tool import analyze_infra_changes
from incident_agent.tools.logs_tool import analyze_logs
from incident_agent.tools.metrics_tool import analyze_metrics


def investigate_incident(
    incident_name: str,
    datasets_root: Path | None = None,
    prefer_llm: bool = True,
) -> IncidentReport:
    """Run investigation workflow with optional LLM synthesis and deterministic fallback."""
    if datasets_root is None:
        datasets_root = Path(__file__).resolve().parents[1] / "datasets" / "incidents"

    target_dir = incident_dir(datasets_root, incident_name)
    metadata_json = load_json(target_dir / "metadata.json")
    metadata = IncidentMetadata(
        incident_name=metadata_json["incident_name"],
        title=metadata_json["title"],
        service_name=metadata_json["service_name"],
    )

    logs = analyze_logs(target_dir / "logs.jsonl")
    metrics = analyze_metrics(target_dir / "metrics.csv")
    deploys = analyze_deploys(target_dir / "deploy_history.json")
    infra = analyze_infra_changes(target_dir / "infra_changes.json")

    should_try_llm = prefer_llm and has_llm_credentials()
    if should_try_llm:
        try:
            return build_report_with_llm(
                metadata=metadata,
                logs=logs,
                metrics=metrics,
                deploys=deploys,
                infra=infra,
            )
        except LLMReasonerError:
            # Preserve local-first behavior by always falling back to deterministic reasoning.
            pass

    return build_deterministic_report(
        metadata=metadata,
        logs=logs,
        metrics=metrics,
        deploys=deploys,
        infra=infra,
    )

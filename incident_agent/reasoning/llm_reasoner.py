"""LLM-backed reasoner for structured incident report generation."""

from __future__ import annotations

import json
from typing import Any

from incident_agent.llm_provider import (
    create_openai_compatible_client,
    get_model_for_provider,
    has_llm_credentials,
)
from incident_agent.models import (
    DeployAnalysis,
    IncidentMetadata,
    IncidentReport,
    InfraAnalysis,
    LogAnalysis,
    MetricsAnalysis,
    TimelineEvent,
)


class LLMReasonerError(Exception):
    """Raised when LLM report generation fails or produces invalid output."""


def _evidence_payload(
    metadata: IncidentMetadata,
    logs: LogAnalysis,
    metrics: MetricsAnalysis,
    deploys: DeployAnalysis,
    infra: InfraAnalysis,
) -> dict[str, Any]:
    """Build a compact, deterministic evidence payload for the LLM."""
    latest_deploy = None
    if deploys.latest_deploy:
        latest_deploy = {
            "timestamp": deploys.latest_deploy.timestamp,
            "version": deploys.latest_deploy.version,
            "service": deploys.latest_deploy.service,
            "notes": deploys.latest_deploy.notes,
        }

    latest_infra = None
    if infra.latest_change:
        latest_infra = {
            "timestamp": infra.latest_change.timestamp,
            "component": infra.latest_change.component,
            "change_type": infra.latest_change.change_type,
            "risk_level": infra.latest_change.risk_level,
            "details": infra.latest_change.details,
        }

    return {
        "incident_name": metadata.incident_name,
        "incident_title": metadata.title,
        "service_name": metadata.service_name,
        "logs": {
            "total_events": logs.total_events,
            "error_events": logs.error_events,
            "db_timeout_events": logs.db_timeout_events,
            "first_timestamp": logs.first_timestamp,
            "last_timestamp": logs.last_timestamp,
            "sample_timeout_messages": logs.sample_timeout_messages,
        },
        "metrics": {
            "error_rate_rising": metrics.error_rate_rising,
            "latency_rising": metrics.latency_rising,
            "peak_error_rate": metrics.peak_error_rate,
            "peak_p95_latency_ms": metrics.peak_p95_latency_ms,
            "latest_point": {
                "timestamp": metrics.points[-1].timestamp,
                "error_rate": metrics.points[-1].error_rate,
                "p95_latency_ms": metrics.points[-1].p95_latency_ms,
            }
            if metrics.points
            else None,
        },
        "deploys": {
            "latest_deploy": latest_deploy,
            "count": len(deploys.records),
        },
        "infra_changes": {
            "latest_change": latest_infra,
            "high_risk_count": len(infra.high_risk_changes),
        },
    }


def validate_and_build_report(payload: dict[str, Any], metadata: IncidentMetadata) -> IncidentReport:
    """Validate strict payload shape and convert it to IncidentReport."""
    required_keys = {
        "likely_root_cause",
        "confidence",
        "key_evidence",
        "timeline",
        "suggested_remediation",
        "next_investigative_steps",
    }
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise LLMReasonerError(f"LLM response missing required keys: {missing}")

    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise LLMReasonerError("confidence must be a number") from exc

    if confidence < 0.0 or confidence > 1.0:
        raise LLMReasonerError("confidence must be between 0.0 and 1.0")

    for key in ["key_evidence", "timeline", "suggested_remediation", "next_investigative_steps"]:
        if not isinstance(payload[key], list):
            raise LLMReasonerError(f"{key} must be a list")

    timeline: list[TimelineEvent] = []
    for item in payload["timeline"]:
        if not isinstance(item, dict):
            raise LLMReasonerError("timeline entries must be objects")
        if not {"timestamp", "event", "source"}.issubset(item.keys()):
            raise LLMReasonerError("timeline entries must contain timestamp, event, and source")
        timeline.append(
            TimelineEvent(
                timestamp=str(item["timestamp"]),
                event=str(item["event"]),
                source=str(item["source"]),
            )
        )

    timeline = sorted(timeline, key=lambda e: e.timestamp)

    return IncidentReport(
        incident_name=metadata.incident_name,
        incident_title=metadata.title,
        service_name=metadata.service_name,
        likely_root_cause=str(payload["likely_root_cause"]),
        confidence=confidence,
        key_evidence=[str(item) for item in payload["key_evidence"]],
        timeline=timeline,
        suggested_remediation=[str(item) for item in payload["suggested_remediation"]],
        next_investigative_steps=[str(item) for item in payload["next_investigative_steps"]],
    )


def build_report_with_llm(
    metadata: IncidentMetadata,
    logs: LogAnalysis,
    metrics: MetricsAnalysis,
    deploys: DeployAnalysis,
    infra: InfraAnalysis,
    model: str | None = None,
    client: Any | None = None,
) -> IncidentReport:
    """Call an LLM for final report synthesis and return strict IncidentReport."""
    if not has_llm_credentials():
        raise LLMReasonerError("No LLM credentials found for the selected provider")

    selected_model = model or get_model_for_provider()

    if client is None:
        try:
            client = create_openai_compatible_client()
        except ValueError as exc:
            raise LLMReasonerError(str(exc)) from exc

    evidence = _evidence_payload(
        metadata=metadata,
        logs=logs,
        metrics=metrics,
        deploys=deploys,
        infra=infra,
    )

    system_prompt = (
        "You are an SRE incident investigator. "
        "Return ONLY valid JSON. "
        "Do not include markdown or extra keys."
    )
    user_prompt = (
        "Generate a structured incident report from the evidence. "
        "Use this exact JSON schema:\n"
        "{"
        '"likely_root_cause": string, '
        '"confidence": number between 0 and 1, '
        '"key_evidence": string[], '
        '"timeline": [{"timestamp": string, "event": string, "source": string}], '
        '"suggested_remediation": string[], '
        '"next_investigative_steps": string[]'
        "}\n"
        "Evidence:\n"
        f"{json.dumps(evidence, sort_keys=True)}"
    )

    try:
        response = client.chat.completions.create(
            model=selected_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        raise LLMReasonerError(f"LLM API request failed: {exc}") from exc

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise LLMReasonerError("LLM returned empty content")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMReasonerError("LLM returned non-JSON response") from exc

    if not isinstance(payload, dict):
        raise LLMReasonerError("LLM response must be a JSON object")

    return validate_and_build_report(payload=payload, metadata=metadata)

"""LLM-backed free chat helpers for major incidents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from incident_agent.llm_provider import (
    create_openai_compatible_client,
    get_model_for_provider,
    has_llm_credentials,
)
from incident_agent.models import MajorIncidentReport


class MajorIncidentChatError(Exception):
    """Raised when major-incident chat setup or querying fails."""


@dataclass
class MajorIncidentChatSession:
    """In-memory chat session bound to a major-incident report context."""

    report: MajorIncidentReport
    history: list[dict[str, str]] = field(default_factory=list)


def _report_context_payload(report: MajorIncidentReport) -> dict[str, Any]:
    top_hyp = report.hypotheses[0] if report.hypotheses else None
    return {
        "group": {
            "id": report.incident_group.group_id,
            "title": report.incident_group.title,
            "severity": report.incident_group.severity,
            "status": report.incident_group.status,
            "commander": report.incident_group.commander,
            "summary": report.incident_group.summary,
        },
        "likely_initiating_fault_service": report.likely_initiating_fault_service,
        "impacted_services_count": report.impacted_services_count,
        "impacted_teams": report.impacted_teams,
        "customer_facing_impact": report.customer_facing_impact,
        "top_hypothesis": {
            "title": top_hyp.title,
            "confidence": top_hyp.confidence,
            "description": top_hyp.description,
            "supporting_evidence": top_hyp.supporting_evidence,
            "contradicting_evidence": top_hyp.contradicting_evidence,
        }
        if top_hyp
        else None,
        "service_summaries": [
            {
                "service": s.service,
                "team": s.team,
                "first_anomaly": s.first_anomaly,
                "likely_role": s.likely_role,
                "confidence": s.confidence,
                "symptoms": s.symptoms,
                "evidence": s.evidence,
            }
            for s in report.service_summaries
        ],
        "recommended_next_actions": report.recommended_next_actions,
        "timeline": [
            {
                "timestamp": e.timestamp,
                "service": e.service,
                "source": e.source,
                "event": e.event,
                "severity": e.severity,
            }
            for e in report.merged_timeline
        ],
    }


def ask_major_incident_question(
    session: MajorIncidentChatSession,
    question: str,
    model: str | None = None,
    client: Any | None = None,
    concise: bool = True,
) -> str:
    """Ask a free-form question grounded in deterministic major-incident data."""
    if not question.strip():
        raise MajorIncidentChatError("Question must be non-empty.")

    if not has_llm_credentials():
        raise MajorIncidentChatError("No LLM credentials found for the selected provider.")

    selected_model = model or get_model_for_provider()
    if client is None:
        try:
            client = create_openai_compatible_client()
        except ValueError as exc:
            raise MajorIncidentChatError(str(exc)) from exc

    context = json.dumps(_report_context_payload(session.report), sort_keys=True)
    messages = [
        {
            "role": "system",
            "content": (
                "You are an incident command assistant. "
                "Answer using only provided major-incident context. "
                "If unknown, say what is unknown and what to validate."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Major incident context (JSON): {context}\n"
                f"Style: {'2-5 lines unless user asks for details' if concise else 'detailed response allowed'}"
            ),
        },
        *session.history,
        {"role": "user", "content": question},
    ]

    try:
        response = client.chat.completions.create(
            model=selected_model,
            temperature=0,
            messages=messages,
        )
    except Exception as exc:
        raise MajorIncidentChatError(f"LLM API request failed: {exc}") from exc

    answer = response.choices[0].message.content if response.choices else None
    if not answer:
        raise MajorIncidentChatError("LLM returned an empty response.")

    cleaned = answer.strip()
    session.history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": cleaned},
        ]
    )
    return cleaned

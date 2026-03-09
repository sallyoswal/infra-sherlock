"""Interactive incident chat helpers backed by OpenAI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from incident_agent.agent import investigate_incident
from incident_agent.llm_provider import (
    create_openai_compatible_client,
    get_model_for_provider,
    has_llm_credentials,
)
from incident_agent.models import IncidentReport

MAX_HISTORY_TURNS = 10


class IncidentChatError(Exception):
    """Raised when chat session setup or querying fails."""


@dataclass
class IncidentChatSession:
    """In-memory chat session bound to a single incident report context."""

    report: IncidentReport
    history: list[dict[str, str]] = field(default_factory=list)


def create_chat_session(
    incident_name: str,
    datasets_root: Path | None = None,
    investigation_mode: Literal["local", "cloud"] = "local",
    service_name: str | None = None,
    incident_title: str | None = None,
) -> IncidentChatSession:
    """Build chat context from an AI-generated incident report."""
    if not has_llm_credentials():
        raise IncidentChatError("No LLM credentials found for the selected provider.")
    report = investigate_incident(
        incident_name=incident_name,
        datasets_root=datasets_root,
        investigation_mode=investigation_mode,
        service_name=service_name,
        incident_title=incident_title,
    )
    return IncidentChatSession(report=report)


def ask_incident_question(
    session: IncidentChatSession,
    question: str,
    model: str | None = None,
    client: Any | None = None,
    concise: bool = True,
    focus_mode: str | None = None,
) -> str:
    """Ask a question about the incident using OpenAI with local report context."""
    if not question.strip():
        raise IncidentChatError("Question must be non-empty.")

    if not has_llm_credentials():
        raise IncidentChatError("No LLM credentials found for the selected provider.")

    selected_model = model or get_model_for_provider()
    if client is None:
        try:
            client = create_openai_compatible_client()
        except ValueError as exc:
            raise IncidentChatError(str(exc)) from exc

    report_json = json.dumps(asdict(session.report), sort_keys=True)
    messages = [
        {
            "role": "system",
            "content": (
                "You are an SRE incident assistant. Answer only using the provided incident report. "
                "If data is missing, explicitly say what is unknown and what to verify next. "
                "Prefer concise, operator-friendly responses. "
                f"Incident report context (JSON): {report_json}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Response style: {'2-4 lines max unless asked for details' if concise else 'detailed explanation allowed'}\\n"
                f"Focus mode: {focus_mode or 'general'}"
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
        raise IncidentChatError(f"LLM API request failed: {exc}") from exc
    answer = response.choices[0].message.content if response.choices else None
    if not answer:
        raise IncidentChatError("OpenAI returned an empty response.")

    cleaned = answer.strip()
    session.history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": cleaned},
        ]
    )
    if len(session.history) > MAX_HISTORY_TURNS * 2:
        session.history = session.history[-(MAX_HISTORY_TURNS * 2):]
    return cleaned

"""Intent classification for interactive incident chat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Intent = Literal[
    "summary",
    "root-cause",
    "timeline",
    "remediation",
    "evidence",
    "help",
    "exit",
    "question",
]


@dataclass
class IntentResult:
    """Classification result for a user chat turn."""

    intent: Intent
    detailed: bool = False


_DETAIL_HINTS = (
    "detail",
    "detailed",
    "deep",
    "deeper",
    "expand",
    "long",
    "longer",
    "explain more",
    "more context",
)


def _is_detailed_request(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in _DETAIL_HINTS)


def classify_user_input(text: str, last_intent: Intent | None = None) -> IntentResult:
    """Map raw user text into a chat intent category."""
    stripped = text.strip()
    lowered = stripped.lower()

    if not stripped:
        return IntentResult(intent="question")

    if lowered in {"/exit", "/quit", "exit", "quit"}:
        return IntentResult(intent="exit")
    if lowered in {"/help", "help"}:
        return IntentResult(intent="help")

    command_map = {
        "/summary": "summary",
        "/root": "root-cause",
        "/timeline": "timeline",
        "/evidence": "evidence",
        "/remediation": "remediation",
    }
    if lowered in command_map:
        return IntentResult(intent=command_map[lowered])

    detailed = _is_detailed_request(lowered)

    if lowered.startswith("/export "):
        return IntentResult(intent="question")

    if any(token in lowered for token in ("timeline", "chronology", "sequence", "when")):
        return IntentResult(intent="timeline", detailed=detailed)

    if any(token in lowered for token in ("how to fix", "fix", "mitigation", "mitigate", "remediation", "what should we do")):
        return IntentResult(intent="remediation", detailed=detailed)

    if any(token in lowered for token in ("evidence", "proof", "signals", "show me evidence")):
        return IntentResult(intent="evidence", detailed=detailed)

    if "why do we think" in lowered or "why do you think" in lowered:
        return IntentResult(intent="evidence", detailed=detailed)

    if any(token in lowered for token in ("root cause", "cause", "what's wrong", "whats wrong", "why")):
        return IntentResult(intent="root-cause", detailed=detailed)

    if any(token in lowered for token in ("summary", "what happened", "give me overview", "overview", "status")):
        return IntentResult(intent="summary", detailed=detailed)

    # Follow-up context memory: short prompts inherit previous mode.
    if len(lowered.split()) <= 3 and last_intent in {
        "summary",
        "root-cause",
        "timeline",
        "remediation",
        "evidence",
    }:
        if lowered in {"why?", "why", "evidence?", "show evidence"}:
            return IntentResult(intent="evidence", detailed=detailed)
        if lowered in {"what should we do?", "next?", "fix?"}:
            return IntentResult(intent="remediation", detailed=detailed)
        if lowered in {"timeline?", "when?"}:
            return IntentResult(intent="timeline", detailed=detailed)
        if lowered in {"details", "more", "expand", "more details"}:
            return IntentResult(intent=last_intent, detailed=True)

    return IntentResult(intent="question", detailed=detailed)

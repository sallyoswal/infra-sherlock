from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def configure_fake_llm(monkeypatch) -> None:
    """Run tests in AI-only mode without making real API calls."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    from incident_agent import agent
    from incident_agent.reasoning.deterministic_reasoner import build_report as build_deterministic_report

    def _fake_llm_report(*, metadata, logs, metrics, deploys, infra):
        return build_deterministic_report(
            metadata=metadata,
            logs=logs,
            metrics=metrics,
            deploys=deploys,
            infra=infra,
        )

    monkeypatch.setattr(agent, "build_report_with_llm", _fake_llm_report)

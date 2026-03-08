from __future__ import annotations

from incident_agent.llm_provider import (
    get_model_for_provider,
    get_provider,
    has_llm_credentials,
)


def test_default_provider_is_openai(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert get_provider() == "openai"


def test_openrouter_provider_uses_openrouter_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert has_llm_credentials() is True
    assert get_model_for_provider() == "meta-llama/llama-3.1-8b-instruct:free"


def test_openai_provider_without_key_returns_false(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert has_llm_credentials() is False

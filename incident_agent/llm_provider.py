"""Provider-aware LLM client helpers for OpenAI-compatible backends."""

from __future__ import annotations

import os
from typing import Literal

Provider = Literal["openai", "openrouter"]


def get_provider() -> Provider:
    """Return selected provider from environment, defaulting to OpenAI."""
    value = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if value == "openrouter":
        return "openrouter"
    return "openai"


def get_provider_api_key(provider: Provider | None = None) -> str | None:
    """Return provider-specific API key from environment."""
    selected = provider or get_provider()
    if selected == "openrouter":
        return os.getenv("OPENROUTER_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def has_llm_credentials() -> bool:
    """Whether credentials for the selected provider are available."""
    key = get_provider_api_key()
    return bool(key and key.strip())


def get_model_for_provider(provider: Provider | None = None) -> str:
    """Return model name for selected provider with practical defaults."""
    selected = provider or get_provider()
    if selected == "openrouter":
        return os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def create_openai_compatible_client(provider: Provider | None = None):
    """Create an OpenAI SDK client for OpenAI or OpenRouter."""
    selected = provider or get_provider()
    api_key = get_provider_api_key(selected)
    if not api_key:
        raise ValueError(f"Missing API key for provider: {selected}")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ValueError("openai package is not installed") from exc

    if selected == "openrouter":
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)

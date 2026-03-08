from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def clear_llm_env() -> None:
    """Keep tests deterministic by defaulting to local/fallback mode."""
    for key in (
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "LLM_PROVIDER",
        "OPENAI_MODEL",
        "OPENROUTER_MODEL",
    ):
        os.environ.pop(key, None)

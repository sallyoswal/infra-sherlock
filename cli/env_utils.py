"""Shared CLI environment helpers."""

from __future__ import annotations

import os
from pathlib import Path


def load_local_env(project_root: Path, env_file: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    target = env_file or (project_root / ".env")
    if not target.exists():
        return

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value

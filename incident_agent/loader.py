"""Dataset loading utilities for local incident scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class IncidentDataError(Exception):
    """Raised when incident data is missing or malformed."""


def load_json(path: Path) -> Any:
    """Load and parse a JSON file with explicit error context."""
    if not path.exists():
        raise IncidentDataError(f"Missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IncidentDataError(f"Invalid JSON in file {path}: {exc}") from exc


def incident_dir(base_dir: Path, incident_name: str) -> Path:
    """Resolve and validate an incident directory."""
    target = base_dir / incident_name
    if not target.exists() or not target.is_dir():
        raise IncidentDataError(f"Incident not found: {incident_name} in {base_dir}")
    return target

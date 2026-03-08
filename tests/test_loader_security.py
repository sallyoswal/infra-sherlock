from __future__ import annotations

from pathlib import Path

import pytest

from incident_agent.loader import IncidentDataError, incident_dir


def test_incident_dir_rejects_path_traversal(tmp_path: Path) -> None:
    incidents_root = tmp_path / "incidents"
    incidents_root.mkdir()

    with pytest.raises(IncidentDataError, match="path traversal"):
        incident_dir(incidents_root, "../../etc")


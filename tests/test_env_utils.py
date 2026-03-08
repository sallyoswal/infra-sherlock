from __future__ import annotations

import warnings
from pathlib import Path

from cli.env_utils import load_local_env


def test_load_local_env_warns_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir(parents=True)

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        load_local_env(project_root, warn_missing=True)

    assert records
    assert ".env file not found" in str(records[0].message)

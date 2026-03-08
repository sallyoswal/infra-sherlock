from __future__ import annotations

import os
import warnings

import cli.watch_incidents as watch_cli


def test_watch_cli_detect_and_notify_runs_once(monkeypatch) -> None:
    captured = {}

    def _fake_run_watch_loop(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(watch_cli, "run_watch_loop", _fake_run_watch_loop)

    code = watch_cli.main(["payments_db_timeout", "--mode", "local", "--detect-and-notify"])

    assert code == 0
    assert captured["once"] is True


def test_watch_cli_once_alias_still_supported(monkeypatch) -> None:
    captured = {}

    def _fake_run_watch_loop(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(watch_cli, "run_watch_loop", _fake_run_watch_loop)

    code = watch_cli.main(["payments_db_timeout", "--mode", "local", "--once"])

    assert code == 0
    assert captured["once"] is True


def test_watch_cli_sets_dry_run_env(monkeypatch) -> None:
    captured = {}

    def _fake_run_watch_loop(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(watch_cli, "run_watch_loop", _fake_run_watch_loop)
    os.environ.pop("PLUGIN_DRY_RUN", None)

    code = watch_cli.main(
        ["payments_db_timeout", "--mode", "local", "--detect-and-notify", "--dry-run"]
    )

    assert code == 0
    assert os.environ.get("PLUGIN_DRY_RUN") == "1"


def test_watch_cli_no_once_deprecation_when_new_flag_present(monkeypatch) -> None:
    def _fake_run_watch_loop(**kwargs):
        del kwargs
        return []

    monkeypatch.setattr(watch_cli, "run_watch_loop", _fake_run_watch_loop)

    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        code = watch_cli.main(
            ["payments_db_timeout", "--mode", "local", "--once", "--detect-and-notify"]
        )

    assert code == 0
    assert not records

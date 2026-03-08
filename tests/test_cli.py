from cli.run_agent import main


def test_cli_investigate_returns_success() -> None:
    code = main(["investigate", "payments_db_timeout"])
    assert code == 0


def test_cli_investigate_writes_markdown_report(tmp_path) -> None:
    output_file = tmp_path / "report.md"
    code = main(["investigate", "payments_db_timeout", "--output", str(output_file)])
    assert code == 0
    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    assert "# Payments API timeout spike after network policy change" in content


def test_cli_timeline_formatting_in_plain_output(monkeypatch, capsys) -> None:
    import cli.run_agent as run_agent_module

    monkeypatch.setattr(run_agent_module, "HAS_RICH", False)
    code = run_agent_module.main(["investigate", "payments_db_timeout"])
    captured = capsys.readouterr()

    assert code == 0
    assert "Timeline:" in captured.out
    assert "[logs]" in captured.out or "[deploy_history]" in captured.out or "[infra_changes]" in captured.out

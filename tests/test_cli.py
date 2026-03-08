from cli.run_agent import main


def test_cli_investigate_returns_success() -> None:
    code = main(["investigate", "payments_db_timeout"])
    assert code == 0

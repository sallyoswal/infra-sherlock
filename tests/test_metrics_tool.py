from pathlib import Path

from incident_agent.tools.metrics_tool import analyze_metrics


def test_analyze_metrics_detects_rising_error_and_latency() -> None:
    metrics_path = Path("datasets/incidents/payments_db_timeout/metrics.csv")
    result = analyze_metrics(metrics_path)

    assert result.error_rate_rising is True
    assert result.latency_rising is True
    assert result.peak_error_rate > 1.0
    assert result.peak_p95_latency_ms > 500


def test_analyze_metrics_detects_spike_and_recover_as_rising(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.csv"
    metrics_path.write_text(
        "timestamp,error_rate,p95_latency_ms\n"
        "2026-03-06T09:00:00Z,1.0,100\n"
        "2026-03-06T09:05:00Z,4.0,300\n"
        "2026-03-06T09:10:00Z,1.1,110\n",
        encoding="utf-8",
    )

    result = analyze_metrics(metrics_path)
    assert result.error_rate_rising is True
    assert result.latency_rising is True

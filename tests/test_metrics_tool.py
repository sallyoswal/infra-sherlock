from pathlib import Path

from incident_agent.tools.metrics_tool import analyze_metrics


def test_analyze_metrics_detects_rising_error_and_latency() -> None:
    metrics_path = Path("datasets/incidents/payments_db_timeout/metrics.csv")
    result = analyze_metrics(metrics_path)

    assert result.error_rate_rising is True
    assert result.latency_rising is True
    assert result.peak_error_rate > 1.0
    assert result.peak_p95_latency_ms > 500

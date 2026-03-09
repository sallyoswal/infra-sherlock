"""Metrics analysis tool for deterministic incident investigation."""

from __future__ import annotations

import csv
from pathlib import Path

from incident_agent.models import MetricPoint, MetricsAnalysis


class MetricsToolError(Exception):
    """Raised when metrics are missing or malformed."""


def analyze_metrics(metrics_path: Path) -> MetricsAnalysis:
    """Analyze metrics CSV and detect error/latency degradation trends."""
    if not metrics_path.exists():
        raise MetricsToolError(f"Metrics file not found: {metrics_path}")

    points: list[MetricPoint] = []
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            points.append(
                MetricPoint(
                    timestamp=row["timestamp"],
                    error_rate=float(row["error_rate"]),
                    p95_latency_ms=float(row["p95_latency_ms"]),
                )
            )

    if not points:
        raise MetricsToolError(f"No metric rows found in {metrics_path}")

    baseline_error_rate = points[0].error_rate
    baseline_latency = points[0].p95_latency_ms
    peak_error_rate = max(p.error_rate for p in points)
    peak_p95_latency_ms = max(p.p95_latency_ms for p in points)

    # Detect incident spikes, including spike-and-recover patterns.
    error_rate_rising = peak_error_rate > baseline_error_rate * 1.5
    latency_rising = peak_p95_latency_ms > baseline_latency * 1.5

    return MetricsAnalysis(
        points=points,
        error_rate_rising=error_rate_rising,
        latency_rising=latency_rising,
        peak_error_rate=peak_error_rate,
        peak_p95_latency_ms=peak_p95_latency_ms,
    )

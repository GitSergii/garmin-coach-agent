"""Unit tests for deterministic weekly-load aggregation."""

import pytest

from src.analytics.context_payload import aggregate_running_week


def test_aggregate_running_week_counts_runs():
    summaries = [
        {"resting_heart_rate": 50},
        {"resting_heart_rate": 52},
    ]
    activities = [
        {
            "activity_type": "running",
            "distance_km": 10.0,
            "duration_seconds": 3600,
        },
        {
            "activity_type": "cycling",
            "distance_km": 40.0,
            "duration_seconds": 5400,
        },
    ]
    out = aggregate_running_week(summaries, activities)
    assert out["run_sessions_count"] == 1
    assert out["total_run_km_week"] == 10.0
    assert out["total_run_duration_hours"] == pytest.approx(1.0)
    assert out["avg_resting_hr_recent"] == 51.0


def test_aggregate_running_week_no_runs():
    out = aggregate_running_week([], [])
    assert out["run_sessions_count"] == 0
    assert out["total_run_duration_hours"] == 0.0

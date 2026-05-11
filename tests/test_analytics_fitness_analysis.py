"""Tests for deterministic fitness analysis payload construction."""

import asyncio

from src.analytics.fitness_analysis import build_fitness_analysis_payload


class _FakeDbTools:
    async def get_daily_summaries(self, user_id, start, end):
        _ = (user_id, start, end)
        return [
            {
                "steps": 12000,
                "sleep_duration_hours": 6.2,
                "stress_level_avg": 58,
                "body_battery_level": 45,
                "resting_heart_rate": 62,
            },
            {
                "steps": 9000,
                "sleep_duration_hours": 6.0,
                "stress_level_avg": 60,
                "body_battery_level": 50,
                "resting_heart_rate": 61,
            },
        ]

    async def get_recent_activities(self, user_id, limit=200, since=None):
        _ = (user_id, limit)
        return [
            {
                "activity_type": "running",
                "distance_km": 8.0,
                "duration_seconds": 3200,
            },
            {
                "activity_type": "running",
                "distance_km": 10.0,
                "duration_seconds": 4200,
            },
        ]


def test_build_fitness_analysis_payload_flags_fatigue():
    payload = asyncio.run(build_fitness_analysis_payload(_FakeDbTools(), "u1"))
    assert payload["load"]["run_sessions_count"] == 2
    assert payload["recommendation_hint"] == "hold_easy_week"
    assert "sleep_debt_risk" in payload["fatigue_flags"]

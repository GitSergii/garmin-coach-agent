"""Deterministic fitness trend analysis payloads for ADK tool use."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from analytics.context_payload import aggregate_running_week
from tools.db_tools import DatabaseTools


def _avg(values: List[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


async def build_fitness_analysis_payload(
    db_tools: DatabaseTools,
    user_id: str,
    *,
    days: int = 21,
    activities_limit: int = 30,
) -> Dict[str, Any]:
    """Compute simple, deterministic trend/load/fatigue indicators."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    summaries = await db_tools.get_daily_summaries(user_id, start, end)
    activities = await db_tools.get_recent_activities(user_id, limit=activities_limit, since=start)
    running = aggregate_running_week(summaries, activities)

    steps = [float(s.get("steps") or 0) for s in summaries if s.get("steps") is not None]
    sleep_hours = [
        float(s.get("sleep_duration_hours") or 0)
        for s in summaries
        if s.get("sleep_duration_hours") is not None
    ]
    stress = [
        float(s.get("stress_level_avg") or 0)
        for s in summaries
        if s.get("stress_level_avg") is not None
    ]
    body_battery = [
        float(s.get("body_battery_level") or 0)
        for s in summaries
        if s.get("body_battery_level") is not None
    ]
    resting_hr = [
        float(s.get("resting_heart_rate") or 0)
        for s in summaries
        if s.get("resting_heart_rate") is not None
    ]

    fatigue_flags: List[str] = []
    avg_sleep = _avg(sleep_hours)
    avg_stress = _avg(stress)
    avg_rhr = _avg(resting_hr)
    if avg_sleep is not None and avg_sleep < 6.5:
        fatigue_flags.append("sleep_debt_risk")
    if avg_stress is not None and avg_stress > 55:
        fatigue_flags.append("elevated_stress")
    if avg_rhr is not None and avg_rhr > 60:
        fatigue_flags.append("elevated_resting_hr")

    intensity_hint = (
        "mostly_easy"
        if running.get("run_sessions_count", 0) <= 4
        else "mixed_with_quality"
    )

    return {
        "window_days": days,
        "load": running,
        "trends": {
            "avg_steps": _avg(steps),
            "avg_sleep_hours": avg_sleep,
            "avg_stress_level": avg_stress,
            "avg_body_battery": _avg(body_battery),
            "avg_resting_hr": avg_rhr,
        },
        "intensity_hint": intensity_hint,
        "fatigue_flags": fatigue_flags,
        "recommendation_hint": (
            "hold_easy_week"
            if fatigue_flags
            else "continue_progressive_overload"
        ),
    }

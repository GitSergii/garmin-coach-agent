"""Assemble a structured fitness context from DB tools (no LLM)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from tools.db_tools import DatabaseTools

logger = logging.getLogger(__name__)


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        try:
            return dt.isoformat()
        except TypeError:
            return str(dt)
    return str(dt)


async def build_coach_context_payload(
    db_tools: DatabaseTools,
    user_id: str,
    *,
    days: int = 7,
    activities_limit: int = 10,
) -> Dict[str, Any]:
    """Return JSON-serializable context: profile, recent summaries, activities."""
    end = datetime.utcnow()
    start = end - timedelta(days=days)

    profile = await db_tools.get_user_profile(user_id)
    summaries = await db_tools.get_daily_summaries(user_id, start, end)
    activities = await db_tools.get_recent_activities(user_id, limit=activities_limit)

    goals = (profile or {}).get("goals") or []

    return {
        "profile": {
            "username": (profile or {}).get("username"),
            "timezone": (profile or {}).get("timezone"),
            "coaching_style": ((profile or {}).get("settings") or {}).get(
                "coaching_style", "balanced"
            ),
        },
        "active_goals": goals,
        "daily_summaries": [
            {
                "date": _iso(s.get("date")),
                "steps": s.get("steps"),
                "distance_km": s.get("distance_km"),
                "active_minutes": s.get("active_minutes"),
                "sleep_duration_hours": s.get("sleep_duration_hours"),
                "sleep_quality_score": s.get("sleep_quality_score"),
                "resting_heart_rate": s.get("resting_heart_rate"),
                "avg_heart_rate": s.get("avg_heart_rate"),
                "stress_level_avg": s.get("stress_level_avg"),
                "body_battery_level": s.get("body_battery_level"),
                "vo2_max": s.get("vo2_max"),
            }
            for s in summaries
        ],
        "recent_activities": [
            {
                "activity_type": a.get("activity_type"),
                "activity_name": a.get("activity_name"),
                "start_time": _iso(a.get("start_time")),
                "duration_seconds": a.get("duration_seconds"),
                "distance_km": a.get("distance_km"),
                "avg_heart_rate": a.get("avg_heart_rate"),
                "max_heart_rate": a.get("max_heart_rate"),
            }
            for a in activities
        ],
        "window": {"start": _iso(start), "end": _iso(end), "days": days},
    }


def aggregate_running_week(
    summaries: List[Dict[str, Any]], activities: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Light aggregates for weekly planning (runs + load proxy)."""

    def _is_run(act: Dict[str, Any]) -> bool:
        t = (act.get("activity_type") or act.get("activity_name") or "").lower()
        return "run" in t or "trail" in t or "track" in t or "virtual" in t

    runs = [a for a in activities if _is_run(a)]
    total_run_km = sum(float(a["distance_km"] or 0) for a in runs)
    total_run_seconds = sum(int(a["duration_seconds"] or 0) for a in runs)

    avg_resting_hr_days = [
        s["resting_heart_rate"]
        for s in summaries
        if s.get("resting_heart_rate") is not None
    ]
    avg_resting_hr = (
        round(sum(avg_resting_hr_days) / len(avg_resting_hr_days), 1)
        if avg_resting_hr_days
        else None
    )

    return {
        "run_sessions_count": len(runs),
        "total_run_km_week": round(total_run_km, 2),
        "total_run_duration_hours": round(total_run_seconds / 3600, 2) if runs else 0.0,
        "avg_resting_hr_recent": avg_resting_hr,
    }

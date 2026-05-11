"""Structured weekly planning hints (deterministic guardrails + Norwegian-style defaults)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from analytics.context_payload import aggregate_running_week
from tools.db_tools import DatabaseTools


async def build_weekly_plan_payload(
    db_tools: DatabaseTools,
    user_id: str,
    *,
    goal_description: str,
    norwegian_method: bool = True,
    max_hours_per_week: float = 8.0,
    history_days: int = 7,
    activities_limit: int = 20,
) -> Dict[str, Any]:
    """
    Combine last-window load with safe progression rules.

    Norwegian-style here means: prioritize easy aerobic volume; one modest quality touch;
    avoid big jumps versus last week.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=history_days)

    summaries = await db_tools.get_daily_summaries(user_id, start, end)
    activities = await db_tools.get_recent_activities(user_id, limit=activities_limit)
    # Keep only activities that fall within the history window to avoid inflated totals.
    window_activities = [
        a for a in activities
        if a.get("start_time") is not None and a["start_time"] >= start
    ]
    week = aggregate_running_week(summaries, window_activities)

    last_km = float(week.get("total_run_km_week") or 0)
    last_hours = float(week.get("total_run_duration_hours") or 0)

    # Cap ambition by operator-provided ceiling and simple progression.
    cap_hours = max(2.5, float(max_hours_per_week))

    if last_hours > 0:
        proposed_hours = min(last_hours * 1.12, max(last_hours + 1.0, last_hours))
    else:
        proposed_hours = min(4.0, cap_hours)

    proposed_hours = min(proposed_hours, cap_hours)

    easy_share = 0.85 if norwegian_method else 0.75
    quality_sessions = 1 if norwegian_method else 1
    structure = []
    structure.append(
        {
            "type": "easy",
            "sessions": 4 if proposed_hours >= 5 else 3,
            "notes": "Aerobic, conversational pace; bulk of weekly volume.",
        }
    )
    if quality_sessions:
        structure.append(
            {
                "type": "quality",
                "sessions": quality_sessions,
                "notes": "Short threshold intervals or fartlek; avoid going to failure.",
            }
        )
    if proposed_hours >= 6:
        structure.append(
            {
                "type": "long_easy",
                "sessions": 1,
                "notes": "Comfortable progressive long run; mostly easy.",
            }
        )

    return {
        "user_goal_text": goal_description,
        "norwegian_method_emphasis": norwegian_method,
        "planned_easy_volume_share_hint": easy_share,
        "last_week_aggregates": week,
        "proposed_hours_next_week": round(proposed_hours, 2),
        "proposed_km_next_week_hint": round(last_km * 1.1, 2) if last_km else None,
        "session_outline": structure,
        "constraints": [
            f"Hard cap roughly {cap_hours:.1f} h running-derived load this week.",
            "Increase weekly volume by roughly 10% vs last week unless under-recovered.",
            "If resting HR climbs for several days or sleep is poor, repeat easy week.",
        ],
    }

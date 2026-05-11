"""Canonical ADK agent definition with module-level skills and tools."""

import json
import os
import pathlib
from typing import Optional

from google import genai
from google.adk import Agent
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools import skill_toolset
from google.adk.tools.tool_context import ToolContext

from analytics.context_payload import build_coach_context_payload
from analytics.fitness_analysis import build_fitness_analysis_payload
from analytics.query_data import run_guarded_nl2sql
from analytics.weekly_plan_builder import build_weekly_plan_payload
from core.config import init_config
from core.database import init_database
from tools.chart_tools import init_chart_tools
from tools.data_tools import init_data_tools
from tools.db_tools import init_database_tools

# ---------------------------------------------------------------------------
# Session state key shared with Runner state_delta injection
# ---------------------------------------------------------------------------
APP_STATE_USER_KEY = "coach_user_id"

# ---------------------------------------------------------------------------
# Module-level dependency initialization
# ---------------------------------------------------------------------------
_config = init_config()
_database = init_database(_config)
_database.create_tables()
_db_tools = init_database_tools(_database, _config)
_data_tools = init_data_tools(None, _db_tools, _config)
_chart_tools = init_chart_tools(_data_tools, _config)
_genai_client = genai.Client(api_key=_config.google_cloud.api_key)
_model_name: str = os.getenv("COACH_ADK_MODEL", "gemini-2.5-flash")
_enable_nl2sql: bool = _config.features.enable_nl2sql
_enable_charts: bool = _config.features.enable_charts

# ---------------------------------------------------------------------------
# Skills — loaded from filesystem at module level
# ---------------------------------------------------------------------------
_SKILLS_DIR = pathlib.Path(__file__).resolve().parents[2] / "skills"

REQUIRED_SKILL_DIRS = [
    "coach-context",
    "fitness-analysis",
    "weekly-plan",
    "query-data-guarded",
    "chart-render",
]


def _load_skills_or_fail(skills_dir: pathlib.Path) -> list:
    if not skills_dir.exists():
        raise RuntimeError(f"Skills directory missing: {skills_dir}")
    loaded = []
    for name in REQUIRED_SKILL_DIRS:
        skill_path = skills_dir / name
        if not skill_path.exists():
            raise RuntimeError(f"Required skill folder missing: {skill_path}")
        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise RuntimeError(f"Required skill file missing: {skill_md}")
        try:
            loaded.append(load_skill_from_dir(str(skill_path)))
        except Exception as exc:  # noqa: BLE001 - hard-fail at startup
            raise RuntimeError(f"Failed to load skill from {skill_path}: {exc}") from exc
    return loaded


_skills = _load_skills_or_fail(_SKILLS_DIR)

# ---------------------------------------------------------------------------
# Tools — defined at module level, dependencies captured via module globals
# ---------------------------------------------------------------------------

def _uid(ctx: ToolContext) -> Optional[str]:
    return ctx.state.get(APP_STATE_USER_KEY)


async def get_context_data(
    days: int = 7,
    activities_limit: int = 10,
    tool_context: ToolContext | None = None,
) -> str:
    """Return recent athlete context: activities, sleep, HR, goals."""
    if tool_context is None:
        return json.dumps({"error": "missing_tool_context"})
    uid = _uid(tool_context)
    if not uid:
        return json.dumps({"error": "missing_coach_user_id"})
    payload = await build_coach_context_payload(
        _db_tools, uid, days=int(days), activities_limit=int(activities_limit)
    )
    return json.dumps(payload, default=str)


async def analyze_fitness(
    days: int = 21,
    activities_limit: int = 30,
    tool_context: ToolContext | None = None,
) -> str:
    """Return fitness trend, load, and fatigue analysis."""
    if tool_context is None:
        return json.dumps({"error": "missing_tool_context"})
    uid = _uid(tool_context)
    if not uid:
        return json.dumps({"error": "missing_coach_user_id"})
    payload = await build_fitness_analysis_payload(
        _db_tools, uid, days=int(days), activities_limit=int(activities_limit)
    )
    return json.dumps(payload, default=str)


async def weekly_plan(
    goal_description: str,
    norwegian_method: bool = True,
    max_hours_per_week: float = 8.0,
    tool_context: ToolContext | None = None,
) -> str:
    """Build a weekly training plan based on goal and recent load."""
    if tool_context is None:
        return json.dumps({"error": "missing_tool_context"})
    uid = _uid(tool_context)
    if not uid:
        return json.dumps({"error": "missing_coach_user_id"})
    payload = await build_weekly_plan_payload(
        _db_tools,
        uid,
        goal_description=goal_description,
        norwegian_method=bool(norwegian_method),
        max_hours_per_week=float(max_hours_per_week),
    )
    return json.dumps(payload, default=str)


def query_data(
    question: str,
    tool_context: ToolContext | None = None,
) -> str:
    """Answer a specific data question by querying stored Garmin data."""
    if not _enable_nl2sql:
        return json.dumps({"error": "nl2sql_disabled", "hint": "Set ENABLE_NL2SQL=true"})
    if tool_context is None:
        return json.dumps({"error": "missing_tool_context"})
    uid = _uid(tool_context)
    if not uid:
        return json.dumps({"error": "missing_coach_user_id"})
    result = run_guarded_nl2sql(
        genai_client=_genai_client,
        model_name=_model_name,
        database=_db_tools.database,
        user_id=uid,
        question=question,
    )
    return json.dumps(result, default=str)


async def render_chart(
    chart_request: str = "dashboard",
    tool_context: ToolContext | None = None,
) -> str:
    """Generate a chart image from a spec string.

    chart_request format: comma-separated key=value pairs.
    Supported keys:
      metric      – daily summary column, e.g. sleep_duration_hours, resting_heart_rate,
                    distance_km, steps, calories_burned, active_minutes, stress_level_avg,
                    body_battery_level, vo2_max
      chart_type  – trend | weekly | activity | dashboard (default: dashboard)
      days        – integer, window for trend charts (default: 14)
      weeks       – integer, window for weekly bar charts (default: 8)
      title       – optional custom chart title

    Examples:
      "metric=sleep_duration_hours,days=14"
      "metric=resting_heart_rate,days=30"
      "metric=distance_km,chart_type=weekly,weeks=8"
      "chart_type=activity"
      "chart_type=dashboard"
    """
    if not _enable_charts:
        return json.dumps({"error": "charts_disabled", "hint": "Set ENABLE_CHARTS=true"})
    if _chart_tools is None:
        return json.dumps({"error": "chart_tools_not_initialized"})
    if tool_context is None:
        return json.dumps({"error": "missing_tool_context"})
    uid = _uid(tool_context)
    if not uid:
        return json.dumps({"error": "missing_coach_user_id"})
    result = await _chart_tools.generate_chart(uid, chart_request)
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# SkillToolset — skills + registered production tools
# ---------------------------------------------------------------------------
_skill_toolset = skill_toolset.SkillToolset(
    skills=_skills,
    additional_tools=[
        FunctionTool(get_context_data),
        FunctionTool(analyze_fitness),
        FunctionTool(weekly_plan),
        FunctionTool(query_data),
        FunctionTool(render_chart),
    ],
)

# ---------------------------------------------------------------------------
# Canonical module-level root_agent definition
# ---------------------------------------------------------------------------
root_agent = Agent(
    model=_model_name,
    name="garmin_coach_agent",
    description="Personal AI running and recovery coach backed by Garmin data.",
    instruction=(
        "You are a concise running and recovery coach for a single self-hosted user. "
        "Use the available skills to handle coaching requests. "
        "Always load the relevant skill before answering data questions. "
        "Keep replies short and Telegram-friendly. "
        "FORMATTING RULES: use plain text, bullet lists, and emoji where helpful. "
        "Never use markdown bold or italic. "
        "BAD: '••Weekly Objective:•• Build base.' or '**Weekly Objective:** Build base.' "
        "GOOD: 'Weekly Objective: Build base.'"
    ),
    tools=[_skill_toolset],
)

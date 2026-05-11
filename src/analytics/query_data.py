"""NL2SQL query service for the ADK `query_data` tool."""

from __future__ import annotations

from typing import Any, Dict

from google import genai

from analytics.sql_guardrails import execute_readonly_query, validate_nl2sql_query
from core.database import Database


def build_nl2sql_prompt(question: str) -> str:
    return f"""
You are a SQL expert for a fitness database. Convert this natural language query to SQL.

User Query: "{question}"

Available tables:
- garmin_daily_summaries (user_id, activity_date, steps, calories_burned, distance_km, sleep_duration_hours, resting_heart_rate)
- garmin_activities (user_id, start_time, activity_type, distance_km, duration_seconds, calories_burned, avg_heart_rate)
- garmin_sleep (user_id, sleep_date, total_sleep_minutes, deep_sleep_minutes, sleep_quality_score)
- garmin_heart_rate (user_id, recorded_at, heart_rate_bpm, heart_rate_zone)

Rules:
1. Always filter by user_id = :user_id (parameterized placeholder, never inline literals)
2. Return only SQL, no explanation
3. Single SELECT statement only
4. Use PostgreSQL-compatible syntax
5. Include ORDER BY when relevant
6. Include LIMIT <= 200
""".strip()


def _clean_sql_response(model_text: str) -> str:
    sql_query = model_text.strip()
    if sql_query.startswith("```sql"):
        sql_query = sql_query[6:]
    if sql_query.startswith("```"):
        sql_query = sql_query[3:]
    if sql_query.endswith("```"):
        sql_query = sql_query[:-3]
    return sql_query.strip()


def run_guarded_nl2sql(
    *,
    genai_client: genai.Client,
    model_name: str,
    database: Database,
    user_id: str,
    question: str,
) -> Dict[str, Any]:
    """Generate SQL from NL, validate strictly, then execute read-only."""
    prompt = build_nl2sql_prompt(question)
    response = genai_client.models.generate_content(model=model_name, contents=prompt)
    sql_query = _clean_sql_response(response.text or "")

    validation_error = validate_nl2sql_query(sql_query)
    if validation_error:
        return {"error": validation_error}

    return execute_readonly_query(database, sql_query, user_id)

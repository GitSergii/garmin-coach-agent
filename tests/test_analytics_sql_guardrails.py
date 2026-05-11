"""Tests for shared NL2SQL guardrails used by ADK tools."""

from src.analytics.sql_guardrails import validate_nl2sql_query


def test_validate_nl2sql_accepts_safe_select():
    sql = (
        "SELECT activity_date, steps FROM garmin_daily_summaries "
        "WHERE user_id = :user_id ORDER BY activity_date DESC LIMIT 30"
    )
    assert validate_nl2sql_query(sql) is None


def test_validate_nl2sql_rejects_disallowed_table():
    sql = "SELECT * FROM users WHERE user_id = :user_id LIMIT 10"
    assert "disallowed table" in validate_nl2sql_query(sql)


def test_validate_nl2sql_rejects_missing_limit():
    sql = "SELECT * FROM garmin_activities WHERE user_id = :user_id"
    assert "must include LIMIT" in validate_nl2sql_query(sql)

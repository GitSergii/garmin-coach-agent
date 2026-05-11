"""
Focused tests for NL2SQL safety validation.
"""

from src.agent.coach_agent import CoachAgent


def _validator():
    agent = CoachAgent.__new__(CoachAgent)
    return agent._validate_nl2sql_query


def test_accepts_safe_select_with_user_filter_and_limit():
    validate = _validator()
    sql = "SELECT activity_date, steps FROM garmin_daily_summaries WHERE user_id = :user_id ORDER BY activity_date DESC LIMIT 30"
    assert validate(sql) is None


def test_rejects_query_without_parameterized_user_filter():
    validate = _validator()
    sql = "SELECT * FROM garmin_daily_summaries ORDER BY activity_date DESC LIMIT 30"
    assert "user_id filter" in validate(sql)


def test_rejects_disallowed_table():
    validate = _validator()
    sql = "SELECT * FROM users WHERE user_id = :user_id LIMIT 10"
    assert "disallowed table" in validate(sql)


def test_rejects_excessive_limit():
    validate = _validator()
    sql = "SELECT * FROM garmin_activities WHERE user_id = :user_id LIMIT 500"
    assert "LIMIT cannot exceed 200" in validate(sql)

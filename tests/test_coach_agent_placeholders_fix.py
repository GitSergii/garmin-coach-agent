"""Tests for de-placeholdered legacy CoachAgent behaviors."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from src.agent.coach_agent import CoachAgent
from core.database import User, UserGoal, UserSettings


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def order_by(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, model_rows):
        self._model_rows = model_rows
        self.added = []
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._model_rows.get(model, []))

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


class _FakeDatabase:
    def __init__(self, session):
        self._session = session

    @contextmanager
    def get_session(self):
        yield self._session


def test_get_user_data_reads_real_settings_and_goals():
    user = SimpleNamespace(id="u-1", first_name="Sergey", username="sergey", timezone="UTC")
    settings = SimpleNamespace(coaching_style="analytical", preferred_metrics=["steps", "sleep"])
    goals = [
        SimpleNamespace(goal_name="Run 10K"),
        SimpleNamespace(goal_name="Sleep 8h"),
    ]
    session = _FakeSession({User: [user], UserSettings: [settings], UserGoal: goals})
    agent = CoachAgent.__new__(CoachAgent)
    agent.database = _FakeDatabase(session)
    agent.logger = SimpleNamespace(error=lambda *args, **kwargs: None)

    result = asyncio.run(agent._get_user_data("u-1"))

    assert result["goals"] == ["Run 10K", "Sleep 8h"]
    assert result["coaching_style"] == "analytical"
    assert result["preferred_metrics"] == ["steps", "sleep"]


def test_get_user_data_returns_empty_structured_defaults_when_missing():
    user = SimpleNamespace(id="u-1", first_name=None, username="sergey", timezone="UTC")
    session = _FakeSession({User: [user], UserSettings: [], UserGoal: []})
    agent = CoachAgent.__new__(CoachAgent)
    agent.database = _FakeDatabase(session)
    agent.logger = SimpleNamespace(error=lambda *args, **kwargs: None)

    result = asyncio.run(agent._get_user_data("u-1"))

    assert result["goals"] == []
    assert result["coaching_style"] is None
    assert result["preferred_metrics"] == []


def test_update_user_goals_creates_goal_when_none_exists():
    session = _FakeSession({UserGoal: []})
    agent = CoachAgent.__new__(CoachAgent)
    agent.database = _FakeDatabase(session)
    agent.logger = SimpleNamespace(error=lambda *args, **kwargs: None)

    result = asyncio.run(agent._update_user_goals("u-1", "set steps goal to 10000 steps"))

    assert result["status"] == "goal_created"
    assert result["goal_type"] == "steps"
    assert session.committed is True
    assert len(session.added) == 1


def test_update_user_goals_returns_error_when_unparseable():
    session = _FakeSession({UserGoal: []})
    agent = CoachAgent.__new__(CoachAgent)
    agent.database = _FakeDatabase(session)
    agent.logger = SimpleNamespace(error=lambda *args, **kwargs: None)

    result = asyncio.run(agent._update_user_goals("u-1", "please improve my goals somehow"))

    assert "error" in result

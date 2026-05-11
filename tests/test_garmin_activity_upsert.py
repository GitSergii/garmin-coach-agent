"""Regression test for Garmin activity upsert behavior."""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.core.garmin_client import GarminClient


def test_store_activity_updates_existing_record_without_insert():
    existing = SimpleNamespace(
        user_id="user-1",
        garmin_activity_id="123456",
        activity_name="Old Name",
        duration_seconds=1200,
    )

    query_mock = Mock()
    query_mock.filter.return_value.first.return_value = existing

    session_mock = Mock()
    session_mock.query.return_value = query_mock

    @contextmanager
    def _session_ctx():
        yield session_mock

    database = Mock()
    database.get_session.side_effect = _session_ctx
    config = SimpleNamespace(security=SimpleNamespace(secret_key="test-secret"))
    client = GarminClient(config, database)

    updated = {
        "activityId": 123456,
        "activityType": {"typeKey": "running"},
        "activityName": "Morning Run Updated",
        "startTimeLocal": "2026-05-01T07:00:00Z",
        "duration": 2000,
    }

    asyncio.run(client._store_activity("user-1", updated))

    assert existing.activity_name == "Morning Run Updated"
    assert existing.duration_seconds == 2000
    session_mock.add.assert_not_called()
    session_mock.commit.assert_called_once()

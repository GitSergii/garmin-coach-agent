"""
Feature tests for activity detail and chart delivery.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.agent.coach_agent import CoachAgent
from src.core.telegram_bot import TelegramBot
from src.tools.chart_tools import ChartTools


class _FakeDbTools:
    async def get_daily_summaries(self, user_id, start_date, end_date):
        return [
            {
                "date": "2026-04-01",
                "steps": 8000,
                "calories_burned": 2300,
                "sleep_duration_hours": 7.2,
                "resting_heart_rate": 52,
                "distance_km": 6.5,
                "active_minutes": 58,
            },
            {
                "date": "2026-04-02",
                "steps": 9100,
                "calories_burned": 2450,
                "sleep_duration_hours": 7.7,
                "resting_heart_rate": 51,
                "distance_km": 7.1,
                "active_minutes": 63,
            },
        ]


class _FakeDataTools:
    def __init__(self):
        self.db_tools = _FakeDbTools()

    async def fetch_activity_details(self, user_id, activity_id):
        return {
            "activity_id": activity_id,
            "splits": [
                {"distance": 1000, "movingDuration": 300, "averageHR": 150},
                {"distance": 1000, "movingDuration": 295, "averageHR": 154},
                {"distance": 1000, "movingDuration": 305, "averageHR": 158},
            ],
        }

    async def fetch_latest_running_activity_details(self, user_id, days_back=30):
        return {"activity_id": "123456789"}


class _FakeDbOnlyTools:
    async def get_activity_by_garmin_id(self, user_id, garmin_activity_id):
        return {"garmin_activity_id": garmin_activity_id, "raw_activity_data": {"activityId": garmin_activity_id}}


class _FakeGarminClientNoDetails:
    async def get_activity_detail_bundle(self, user_id, garmin_activity_id):
        return None


def test_extract_activity_id_from_message():
    agent = CoachAgent.__new__(CoachAgent)
    assert agent._extract_activity_id("show activity 123456789 details") == "123456789"
    assert agent._extract_activity_id("Please analyze activity-id: 555555") == "555555"
    assert agent._extract_activity_id("show my latest run details") is None


def test_intent_routes_chart_requests():
    agent = CoachAgent.__new__(CoachAgent)
    intent, tools = asyncio.run(agent._analyze_intent("Generate dashboard chart for my week", None))
    assert intent == "chart_request"
    assert "generate_chart" in tools


def test_generate_dashboard_chart_contract(tmp_path):
    chart_tools = ChartTools(_FakeDataTools(), SimpleNamespace())
    chart_tools.output_dir = Path(tmp_path)

    result = asyncio.run(chart_tools.generate_multi_metric_dashboard("user-1", 7))

    assert "error" not in result
    assert result["chart_type"] == "multi_metric_dashboard"
    assert Path(result["chart_path"]).exists()


def test_generate_running_chart_contract(tmp_path):
    chart_tools = ChartTools(_FakeDataTools(), SimpleNamespace())
    chart_tools.output_dir = Path(tmp_path)

    result = asyncio.run(chart_tools.generate_running_activity_chart("user-1", "123456789"))

    assert "error" not in result
    assert result["chart_type"] == "running_activity_detail"
    assert Path(result["chart_path"]).exists()


def test_fetch_activity_details_falls_back_to_db_when_detail_api_unavailable():
    from src.tools.data_tools import DataTools

    tools = DataTools(_FakeGarminClientNoDetails(), _FakeDbOnlyTools(), SimpleNamespace())
    result = asyncio.run(tools.fetch_activity_details("user-1", "777777"))

    assert result["source"] == "database"
    assert result["activity"]["garmin_activity_id"] == "777777"
    assert result["splits"] == []


def test_send_chart_image_helper(tmp_path):
    chart_file = Path(tmp_path) / "sample_chart.png"
    chart_file.write_bytes(b"fake-image-content")

    update = Mock()
    update.message = Mock()
    update.message.reply_photo = AsyncMock()

    response = SimpleNamespace(
        has_charts=True,
        chart_data={"chart_path": str(chart_file), "caption": "Sample chart"},
    )

    bot = TelegramBot(
        config=Mock(),
        database=Mock(),
        coach_agent=Mock(),
        data_tools=Mock(),
        db_tools=Mock(),
        analysis_tools=Mock(),
    )

    asyncio.run(bot._send_chart_if_available(update, response))

    update.message.reply_photo.assert_awaited_once()

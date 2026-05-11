"""
Focused tests for single-owner Telegram access control.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.ext import ApplicationHandlerStop

from src.core.telegram_bot import TelegramBot


def _make_bot(owner_user_id=None, owner_chat_id=None, bind_on_first_start=True):
    config = SimpleNamespace(
        telegram=SimpleNamespace(
            owner_user_id=owner_user_id,
            owner_chat_id=owner_chat_id,
            bind_on_first_start=bind_on_first_start,
            unauthorized_repo_url="https://github.com/GitSergii/Garmin-Coach",
        )
    )
    database = Mock()
    database.try_bind_telegram_owner.return_value = True
    database.get_telegram_owner_binding.return_value = None
    return TelegramBot(
        config=config,
        database=database,
        coach_agent=Mock(),
        data_tools=Mock(),
        db_tools=Mock(),
        analysis_tools=Mock(),
    )


def _make_update(user_id: int, chat_id: int, chat_type: str = "private"):
    reply_text = AsyncMock()
    effective_message = SimpleNamespace(reply_text=reply_text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=effective_message,
        callback_query=None,
    )


def test_first_start_binds_owner_and_persists_keys():
    bot = _make_bot(owner_user_id=None, owner_chat_id=None, bind_on_first_start=True)
    update = _make_update(user_id=101, chat_id=202)

    allowed = asyncio.run(bot._authorize_update(update, allow_first_bind=True))

    assert allowed is True
    assert bot.owner_user_id == 101
    assert bot.owner_chat_id == 202
    bot.database.try_bind_telegram_owner.assert_called_once_with(101, 202)


def test_non_owner_gets_friendly_unauthorized_message():
    bot = _make_bot(owner_user_id=101, owner_chat_id=202, bind_on_first_start=True)
    update = _make_update(user_id=999, chat_id=888)

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot._authorize_update(update))

    update.effective_message.reply_text.assert_awaited_once()
    sent_message = update.effective_message.reply_text.await_args.args[0]
    assert "private for my personal coaching setup" in sent_message
    assert "https://github.com/GitSergii/Garmin-Coach" in sent_message


def test_group_chat_is_blocked_even_for_owner():
    bot = _make_bot(owner_user_id=101, owner_chat_id=202, bind_on_first_start=True)
    update = _make_update(user_id=101, chat_id=202, chat_type="group")

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(bot._authorize_update(update))

    update.effective_message.reply_text.assert_awaited_once()


def test_first_bind_race_falls_back_to_existing_owner():
    bot = _make_bot(owner_user_id=None, owner_chat_id=None, bind_on_first_start=True)
    bot.database.try_bind_telegram_owner.return_value = False
    bot.database.get_telegram_owner_binding.return_value = {"user_id": 555, "chat_id": 777}
    update = _make_update(user_id=555, chat_id=777)

    allowed = asyncio.run(bot._authorize_update(update, allow_first_bind=True))

    assert allowed is True


def test_plain_message_auto_binds_and_creates_user_without_setup():
    bot = _make_bot(owner_user_id=None, owner_chat_id=None, bind_on_first_start=True)
    update = _make_update(user_id=101, chat_id=202)
    update.effective_user.username = "owner"
    update.effective_user.first_name = "Owner"
    update.message = SimpleNamespace(text="How is my training?", reply_text=AsyncMock())

    bot._get_user_id = AsyncMock(return_value=None)
    created_user = SimpleNamespace(id="user-1")
    bot._get_or_create_user = AsyncMock(return_value=created_user)
    response = SimpleNamespace(
        text="You are on track.",
        response_time_ms=12.0,
        tokens_used=None,
        has_charts=False,
    )
    bot.coach_agent.process_message = AsyncMock(return_value=response)
    bot.db_tools.log_api_usage = AsyncMock()
    context = SimpleNamespace(bot=SimpleNamespace(send_chat_action=AsyncMock()))

    asyncio.run(bot.handle_message(update, context))

    bot.database.try_bind_telegram_owner.assert_called_once_with(101, 202)
    bot._get_or_create_user.assert_awaited_once_with(101, "owner", "Owner")
    bot.coach_agent.process_message.assert_awaited_once_with("user-1", "How is my training?")
    update.message.reply_text.assert_awaited_once_with("You are on track.")

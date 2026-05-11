#!/usr/bin/env python3
"""
Reset persisted Telegram owner binding.

Usage:
  ./.venv/bin/python scripts/reset_owner_binding.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.config import init_config
from core.database import init_database

OWNER_USER_SETTING_KEY = "telegram_owner_user_id"
OWNER_CHAT_SETTING_KEY = "telegram_owner_chat_id"
OWNER_BINDING_SETTING_KEY = "telegram_owner_binding"


def main() -> int:
    env_file = os.getenv("APP_ENV_FILE")
    config = init_config(env_file=env_file)
    database = init_database(config)

    database.delete_app_setting(OWNER_USER_SETTING_KEY)
    database.delete_app_setting(OWNER_CHAT_SETTING_KEY)
    database.delete_app_setting(OWNER_BINDING_SETTING_KEY)

    print("Owner binding cleared from database.")
    print("Next private /start can bind a new owner (if TELEGRAM_BIND_ON_FIRST_START=true).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

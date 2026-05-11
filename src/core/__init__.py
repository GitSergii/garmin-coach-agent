"""
Core Infrastructure Components
==============================

This package contains the core infrastructure components for the AI GarminCoach system:
- Configuration management
- Database connection and models
- Garmin API client wrapper
- Telegram bot handler
"""

from .config import Config
from .database import Database

__all__ = ["Config", "Database"] 
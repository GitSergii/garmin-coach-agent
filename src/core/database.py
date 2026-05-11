"""
Database Connection and Models
==============================

Comprehensive database system for the AI GarminCoach application.
Handles PostgreSQL connections, SQLAlchemy models, and database operations.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean, DateTime, 
    Text, JSON, BigInteger, ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.exc import IntegrityError
from contextlib import contextmanager

from core.config import Config

# Configure logging
logger = logging.getLogger(__name__)

# SQLAlchemy Base
Base = declarative_base()


class TimestampMixin:
    """Mixin to add timestamp columns to models."""
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)


class User(Base):
    """User accounts with Garmin credentials."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    
    # Garmin credentials (encrypted by application layer before persistence)
    garmin_username = Column(String(100), nullable=True)
    garmin_password = Column(Text, nullable=True)
    garmin_session_token = Column(Text, nullable=True)
    
    # User status and settings
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    goals = relationship("UserGoal", back_populates="user")
    conversations = relationship("ConversationSession", back_populates="user")
    garmin_daily_summaries = relationship("GarminDailySummary", back_populates="user")
    garmin_activities = relationship("GarminActivity", back_populates="user")
    garmin_heart_rate = relationship("GarminHeartRate", back_populates="user")
    garmin_sleep = relationship("GarminSleep", back_populates="user")


class UserSettings(Base, TimestampMixin):
    """User personalization preferences and coaching settings."""
    __tablename__ = "user_settings"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Coaching preferences
    coaching_style = Column(String(50), default="balanced", nullable=False)  # motivational, analytical, balanced
    preferred_metrics = Column(ARRAY(String), default=["steps", "heart_rate", "sleep"], nullable=False)
    reminder_frequency = Column(String(20), default="daily", nullable=False)  # daily, weekly, monthly
    
    # Notification settings
    enable_daily_summary = Column(Boolean, default=True, nullable=False)
    enable_goal_reminders = Column(Boolean, default=True, nullable=False)
    enable_achievement_alerts = Column(Boolean, default=True, nullable=False)
    enable_health_insights = Column(Boolean, default=True, nullable=False)
    
    # Display preferences
    use_metric_units = Column(Boolean, default=True, nullable=False)
    chart_style = Column(String(20), default="modern", nullable=False)  # modern, minimal, detailed
    
    # Advanced settings
    data_sync_frequency = Column(String(20), default="daily", nullable=False)
    max_chart_history_days = Column(Integer, default=30, nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="settings")


class UserGoal(Base, TimestampMixin):
    """User fitness goals and achievement tracking."""
    __tablename__ = "user_goals"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Goal details
    goal_type = Column(String(50), nullable=False)  # steps, distance, weight, heart_rate, sleep
    goal_name = Column(String(200), nullable=False)
    target_value = Column(Float, nullable=False)
    current_value = Column(Float, default=0.0, nullable=False)
    unit = Column(String(20), nullable=False)  # steps, km, kg, bpm, hours
    
    # Timeline
    target_date = Column(DateTime(timezone=True), nullable=True)
    start_date = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    achieved_date = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    status = Column(String(20), default="active", nullable=False)  # active, completed, paused, cancelled
    priority = Column(String(20), default="medium", nullable=False)  # low, medium, high
    
    # Progress tracking
    progress_percentage = Column(Float, default=0.0, nullable=False)
    best_streak_days = Column(Integer, default=0, nullable=False)
    current_streak_days = Column(Integer, default=0, nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="goals")
    
    __table_args__ = (
        Index("idx_user_goals_user_active", "user_id", "status"),
    )


class ConversationSession(Base, TimestampMixin):
    """Chat session context and AI summaries."""
    __tablename__ = "conversation_sessions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Session details
    session_start = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    session_end = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # AI context
    conversation_summary = Column(Text, nullable=True)
    primary_topics = Column(ARRAY(String), nullable=True)
    user_intent = Column(String(100), nullable=True)
    
    # Metrics
    total_messages = Column(Integer, default=0, nullable=False)
    total_ai_responses = Column(Integer, default=0, nullable=False)
    avg_response_time_ms = Column(Float, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="session")
    
    __table_args__ = (
        Index("idx_conv_sessions_user_active", "user_id", "is_active"),
    )


class ConversationMessage(Base, TimestampMixin):
    """Individual message history with intent tracking."""
    __tablename__ = "conversation_messages"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(UUID(as_uuid=False), ForeignKey("conversation_sessions.id"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Message details
    message_type = Column(String(20), nullable=False)  # user_message, ai_response, system_message
    message_text = Column(Text, nullable=False)
    message_intent = Column(String(100), nullable=True)
    
    # AI response metadata
    ai_model_used = Column(String(50), nullable=True)
    response_time_ms = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    
    # Features used
    tools_used = Column(ARRAY(String), nullable=True)
    charts_generated = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
    
    __table_args__ = (
        Index("idx_conv_messages_session_time", "session_id", "created_at"),
        Index("idx_conv_messages_user_time", "user_id", "created_at"),
    )


class GarminDailySummary(Base, TimestampMixin):
    """Daily activity aggregates from Garmin."""
    __tablename__ = "garmin_daily_summaries"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Date and basic metrics
    activity_date = Column(DateTime(timezone=True), nullable=False)
    steps = Column(Integer, nullable=True)
    calories_burned = Column(Float, nullable=True)
    active_minutes = Column(Integer, nullable=True)
    distance_km = Column(Float, nullable=True)
    
    # Sleep metrics
    sleep_duration_hours = Column(Float, nullable=True)
    sleep_quality_score = Column(Float, nullable=True)
    deep_sleep_minutes = Column(Integer, nullable=True)
    rem_sleep_minutes = Column(Integer, nullable=True)
    
    # Heart rate metrics
    resting_heart_rate = Column(Integer, nullable=True)
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)
    
    # Advanced metrics
    stress_level_avg = Column(Float, nullable=True)
    body_battery_level = Column(Integer, nullable=True)
    vo2_max = Column(Float, nullable=True)
    
    # Data completeness
    data_completeness_percentage = Column(Float, default=0.0, nullable=False)
    sync_status = Column(String(20), default="pending", nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="garmin_daily_summaries")
    
    __table_args__ = (
        Index("idx_daily_summaries_user_date", "user_id", "activity_date"),
        UniqueConstraint("user_id", "activity_date", name="uq_user_daily_summary"),
    )


class GarminActivity(Base, TimestampMixin):
    """Individual workout/activity sessions."""
    __tablename__ = "garmin_activities"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Activity identifiers
    garmin_activity_id = Column(String(50), unique=True, nullable=False)
    activity_type = Column(String(50), nullable=False)  # running, cycling, swimming, etc.
    activity_name = Column(String(200), nullable=True)
    
    # Timing
    start_time = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=False)
    
    # Performance metrics
    distance_km = Column(Float, nullable=True)
    avg_speed_kmh = Column(Float, nullable=True)
    max_speed_kmh = Column(Float, nullable=True)
    calories_burned = Column(Float, nullable=True)
    
    # Heart rate data
    avg_heart_rate = Column(Integer, nullable=True)
    max_heart_rate = Column(Integer, nullable=True)
    heart_rate_zones = Column(JSONB, nullable=True)
    
    # Advanced metrics
    elevation_gain_m = Column(Float, nullable=True)
    training_effect_aerobic = Column(Float, nullable=True)
    training_effect_anaerobic = Column(Float, nullable=True)
    
    # Raw data
    raw_activity_data = Column(JSONB, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="garmin_activities")
    
    __table_args__ = (
        Index("idx_garmin_activities_user_start", "user_id", "start_time"),
        Index("idx_garmin_activities_type", "activity_type"),
        Index("idx_garmin_activities_garmin_id", "garmin_activity_id"),
    )


class GarminHeartRate(Base, TimestampMixin):
    """Heart rate data from Garmin devices."""
    __tablename__ = "garmin_heart_rate"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Heart rate measurement
    recorded_at = Column(DateTime(timezone=True), nullable=False)
    heart_rate_bpm = Column(Integer, nullable=False)
    heart_rate_zone = Column(String(20), nullable=True)  # rest, fat_burn, cardio, peak
    
    # Context
    activity_type = Column(String(50), nullable=True)  # resting, exercise, recovery
    confidence_level = Column(Float, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="garmin_heart_rate")
    
    __table_args__ = (
        Index("idx_garmin_heart_rate_user_time", "user_id", "recorded_at"),
    )


class GarminSleep(Base, TimestampMixin):
    """Sleep data from Garmin devices."""
    __tablename__ = "garmin_sleep"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Sleep period
    sleep_date = Column(DateTime(timezone=True), nullable=False)
    sleep_start_time = Column(DateTime(timezone=True), nullable=False)
    sleep_end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Sleep duration (in minutes)
    total_sleep_minutes = Column(Integer, nullable=False)
    deep_sleep_minutes = Column(Integer, nullable=True)
    light_sleep_minutes = Column(Integer, nullable=True)
    rem_sleep_minutes = Column(Integer, nullable=True)
    awake_minutes = Column(Integer, nullable=True)
    
    # Sleep quality metrics
    sleep_quality_score = Column(Float, nullable=True)  # 0-100
    restfulness_score = Column(Float, nullable=True)
    
    # Raw sleep data
    raw_sleep_data = Column(JSONB, nullable=True)
    
    # Relationship
    user = relationship("User", back_populates="garmin_sleep")
    
    __table_args__ = (
        Index("idx_garmin_sleep_user_date", "user_id", "sleep_date"),
        UniqueConstraint("user_id", "sleep_date", name="uq_user_sleep_date"),
    )


class AIResponseCache(Base, TimestampMixin):
    """Cache AI responses to reduce costs."""
    __tablename__ = "ai_response_cache"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    
    # Cache key components
    query_type = Column(String(100), nullable=False)
    query_hash = Column(String(64), nullable=False)
    date_range_start = Column(DateTime(timezone=True), nullable=True)
    date_range_end = Column(DateTime(timezone=True), nullable=True)
    
    # Cached response
    response_text = Column(Text, nullable=False)
    chart_data = Column(JSONB, nullable=True)
    confidence_score = Column(Float, nullable=True)
    
    # Cache metadata
    cache_hits = Column(Integer, default=0, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    __table_args__ = (
        Index("idx_ai_cache_user_query", "user_id", "query_type", "query_hash"),
        Index("idx_ai_cache_expires", "expires_at"),
    )


class APIUsageLog(Base, TimestampMixin):
    """Track API costs and performance metrics."""
    __tablename__ = "api_usage_log"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    
    # API call details
    api_service = Column(String(50), nullable=False)  # google_genai, garmin_connect, telegram
    feature_used = Column(String(100), nullable=False)
    response_time_ms = Column(Float, nullable=False)
    
    # Cost tracking
    tokens_used = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    
    # Performance metrics
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)
    
    __table_args__ = (
        Index("idx_api_usage_service_time", "api_service", "created_at"),
        Index("idx_api_usage_cost", "estimated_cost_usd"),
    )


class AppSetting(Base, TimestampMixin):
    """Application-level key/value settings."""
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


TELEGRAM_OWNER_BINDING_KEY = "telegram_owner_binding"


class Database:
    """
    Main database management class.
    
    Handles connections, sessions, and provides high-level database operations.
    """
    
    def __init__(self, config: Config):
        """Initialize database with configuration."""
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self._setup_database()
    
    def _setup_database(self):
        """Set up database engine and session factory."""
        try:
            # Create engine with connection pooling
            self.engine = create_engine(
                self.config.database.url,
                pool_size=self.config.database.pool_size,
                max_overflow=self.config.database.max_overflow,
                pool_pre_ping=True,  # Verify connections before use
                echo=self.config.database.echo,
                future=True  # Use SQLAlchemy 2.0 style
            )
            
            # Create session factory
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                future=True
            )
            
            logger.info("Database connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def create_tables(self):
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def drop_tables(self):
        """Drop all database tables (use with caution)."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error(f"Failed to drop database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Session:
        """
        Get a database session with automatic cleanup.
        
        Usage:
            with database.get_session() as session:
                # Use session here
                pass
        """
        session = self.SessionLocal()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_user_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        """Get user by Telegram ID."""
        with self.get_session() as session:
            return session.query(User).filter(User.telegram_user_id == telegram_user_id).first()
    
    def create_user(self, telegram_user_id: int, **kwargs) -> User:
        """Create a new user."""
        with self.get_session() as session:
            user = User(telegram_user_id=telegram_user_id, **kwargs)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    
    def get_active_conversation(self, user_id: uuid.UUID) -> Optional[ConversationSession]:
        """Get active conversation session for user."""
        with self.get_session() as session:
            return session.query(ConversationSession).filter(
                ConversationSession.user_id == user_id,
                ConversationSession.is_active == True
            ).first()
    
    def cleanup_old_data(self, retention_days: int = 90):
        """Clean up old data based on retention policy."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        with self.get_session() as session:
            # Clean up old conversation messages
            deleted_messages = session.query(ConversationMessage).filter(
                ConversationMessage.created_at < cutoff_date
            ).delete()
            
            # Clean up expired cache entries
            deleted_cache = session.query(AIResponseCache).filter(
                AIResponseCache.expires_at < datetime.now(timezone.utc)
            ).delete()
            
            # Clean up old API usage logs
            deleted_logs = session.query(APIUsageLog).filter(
                APIUsageLog.created_at < cutoff_date
            ).delete()
            
            session.commit()
            
            logger.info(f"Cleanup completed: {deleted_messages} messages, {deleted_cache} cache entries, {deleted_logs} logs")

    def get_app_setting(self, key: str) -> Optional[str]:
        """Get an application setting by key."""
        with self.get_session() as session:
            setting = session.query(AppSetting).filter(AppSetting.key == key).first()
            return setting.value if setting else None

    def set_app_setting(self, key: str, value: str) -> None:
        """Create or update an application setting."""
        with self.get_session() as session:
            setting = session.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                setting.value = value
            else:
                session.add(AppSetting(key=key, value=value))
            session.commit()

    def delete_app_setting(self, key: str) -> None:
        """Delete an application setting by key."""
        with self.get_session() as session:
            setting = session.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                session.delete(setting)
                session.commit()

    def get_telegram_owner_binding(self) -> Optional[Dict[str, int]]:
        """Get Telegram owner binding from app settings."""
        raw = self.get_app_setting(TELEGRAM_OWNER_BINDING_KEY)
        if not raw:
            return None
        try:
            user_id_text, chat_id_text = raw.split(":", 1)
            return {"user_id": int(user_id_text), "chat_id": int(chat_id_text)}
        except (ValueError, TypeError):
            logger.warning("Invalid telegram owner binding value in app settings")
            return None

    def try_bind_telegram_owner(self, user_id: int, chat_id: int) -> bool:
        """
        Atomically bind Telegram owner on first claim.

        Returns True only when this call creates the binding.
        """
        with self.get_session() as session:
            existing = session.query(AppSetting).filter(AppSetting.key == TELEGRAM_OWNER_BINDING_KEY).first()
            if existing:
                return False
            session.add(AppSetting(key=TELEGRAM_OWNER_BINDING_KEY, value=f"{user_id}:{chat_id}"))
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False


# Global database instance
database = None

def get_database(config: Config = None) -> Database:
    """Get the global database instance."""
    global database
    if database is None:
        if config is None:
            from core.config import get_config
            config = get_config()
        database = Database(config)
    return database


def init_database(config: Config) -> Database:
    """Initialize the global database instance."""
    global database
    database = Database(config)
    return database 
"""
Database Tools for AI Coach Agent
=================================

This module provides database operation tools for the AI coaching agent.
All database interactions are handled through these tools.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session

from core.database import (
    Database, User, UserSettings, UserGoal, ConversationSession, 
    ConversationMessage, GarminDailySummary, GarminActivity, 
    GarminHeartRate, GarminSleep, AIResponseCache, APIUsageLog
)
from core.config import Config


logger = logging.getLogger(__name__)


class DatabaseTools:
    """
    Database operation tools for the AI coaching agent.
    
    Provides clean interfaces for:
    - User management and settings
    - Conversation history and context
    - Garmin data storage and retrieval
    - Goal tracking and progress
    - Performance and usage monitoring
    """
    
    def __init__(self, database: Database, config: Config):
        """Initialize database tools."""
        self.database = database
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    # User Management Tools
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get complete user profile with settings and goals."""
        try:
            with self.database.get_session() as session:
                user = session.query(User).filter(User.id == user_id).first()
                if not user:
                    return None
                
                # Get user settings
                settings = session.query(UserSettings).filter(
                    UserSettings.user_id == user_id
                ).first()
                
                # Get active goals
                goals = session.query(UserGoal).filter(
                    and_(
                        UserGoal.user_id == user_id,
                        UserGoal.status == 'active'
                    )
                ).all()
                
                return {
                    "id": str(user.id),
                    "telegram_user_id": user.telegram_user_id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "is_premium": user.is_premium,
                    "timezone": user.timezone,
                    "language": user.language,
                    "last_login": user.last_login,
                    "settings": {
                        "coaching_style": settings.coaching_style if settings else "balanced",
                        "preferred_metrics": settings.preferred_metrics if settings else ["steps", "heart_rate", "sleep"],
                        "reminder_frequency": settings.reminder_frequency if settings else "daily",
                        "enable_daily_summary": settings.enable_daily_summary if settings else True,
                        "enable_goal_reminders": settings.enable_goal_reminders if settings else True,
                        "use_metric_units": settings.use_metric_units if settings else True,
                        "chart_style": settings.chart_style if settings else "modern",
                        "data_sync_frequency": settings.data_sync_frequency if settings else "daily",
                        "max_chart_history_days": settings.max_chart_history_days if settings else 30,
                    },
                    "goals": [
                        {
                            "id": str(goal.id),
                            "goal_type": goal.goal_type,
                            "goal_name": goal.goal_name,
                            "target_value": goal.target_value,
                            "current_value": goal.current_value,
                            "unit": goal.unit,
                            "target_date": goal.target_date,
                            "status": goal.status,
                            "priority": goal.priority,
                            "progress_percentage": goal.progress_percentage,
                            "current_streak_days": goal.current_streak_days,
                            "best_streak_days": goal.best_streak_days,
                        } for goal in goals
                    ]
                }
        except Exception as e:
            self.logger.error(f"Error getting user profile for {user_id}: {e}")
            return None
    
    async def update_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Update user settings."""
        try:
            with self.database.get_session() as session:
                user_settings = session.query(UserSettings).filter(
                    UserSettings.user_id == user_id
                ).first()
                
                if not user_settings:
                    # Create new settings
                    user_settings = UserSettings(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        **settings
                    )
                    session.add(user_settings)
                else:
                    # Update existing settings
                    for key, value in settings.items():
                        if hasattr(user_settings, key):
                            setattr(user_settings, key, value)
                
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating user settings for {user_id}: {e}")
            return False
    
    async def create_user_goal(self, user_id: str, goal_data: Dict[str, Any]) -> Optional[str]:
        """Create a new user goal."""
        try:
            with self.database.get_session() as session:
                goal = UserGoal(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    goal_type=goal_data["goal_type"],
                    goal_name=goal_data["goal_name"],
                    target_value=goal_data["target_value"],
                    unit=goal_data["unit"],
                    target_date=goal_data.get("target_date"),
                    priority=goal_data.get("priority", "medium"),
                    status="active"
                )
                session.add(goal)
                session.commit()
                return str(goal.id)
                
        except Exception as e:
            self.logger.error(f"Error creating goal for user {user_id}: {e}")
            return None
    
    async def update_goal_progress(self, goal_id: str, current_value: float, update_streak: bool = True) -> bool:
        """Update goal progress."""
        try:
            with self.database.get_session() as session:
                goal = session.query(UserGoal).filter(UserGoal.id == goal_id).first()
                if not goal:
                    return False
                
                goal.current_value = current_value
                goal.progress_percentage = min(100.0, (current_value / goal.target_value) * 100)
                
                if update_streak:
                    # Update streak logic (simplified)
                    goal.current_streak_days += 1
                    if goal.current_streak_days > goal.best_streak_days:
                        goal.best_streak_days = goal.current_streak_days
                
                if goal.progress_percentage >= 100:
                    goal.status = "completed"
                    goal.achieved_date = datetime.utcnow()
                
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating goal progress for {goal_id}: {e}")
            return False
    
    # Conversation Management Tools
    
    async def get_conversation_history(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent conversation history for a user."""
        try:
            with self.database.get_session() as session:
                # Get recent messages
                messages = session.query(ConversationMessage).filter(
                    ConversationMessage.user_id == user_id
                ).order_by(desc(ConversationMessage.created_at)).limit(limit).all()
                
                return [
                    {
                        "id": str(msg.id),
                        "session_id": str(msg.session_id),
                        "message_type": msg.message_type,
                        "message_text": msg.message_text,
                        "message_intent": msg.message_intent,
                        "ai_model_used": msg.ai_model_used,
                        "response_time_ms": msg.response_time_ms,
                        "tools_used": msg.tools_used,
                        "created_at": msg.created_at
                    } for msg in reversed(messages)
                ]
                
        except Exception as e:
            self.logger.error(f"Error getting conversation history for {user_id}: {e}")
            return []
    
    async def get_conversation_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation session summary."""
        try:
            with self.database.get_session() as session:
                conv_session = session.query(ConversationSession).filter(
                    ConversationSession.id == session_id
                ).first()
                
                if not conv_session:
                    return None
                
                return {
                    "id": str(conv_session.id),
                    "user_id": str(conv_session.user_id),
                    "session_start": conv_session.session_start,
                    "session_end": conv_session.session_end,
                    "is_active": conv_session.is_active,
                    "conversation_summary": conv_session.conversation_summary,
                    "primary_topics": conv_session.primary_topics,
                    "user_intent": conv_session.user_intent,
                    "total_messages": conv_session.total_messages,
                    "total_ai_responses": conv_session.total_ai_responses,
                    "avg_response_time_ms": conv_session.avg_response_time_ms
                }
                
        except Exception as e:
            self.logger.error(f"Error getting conversation summary for {session_id}: {e}")
            return None
    
    # Garmin Data Storage Tools
    
    async def store_daily_summary(self, user_id: str, date: datetime, data: Dict[str, Any]) -> bool:
        """Store daily summary data."""
        try:
            with self.database.get_session() as session:
                # Check if data already exists
                existing = session.query(GarminDailySummary).filter(
                    and_(
                        GarminDailySummary.user_id == user_id,
                        func.date(GarminDailySummary.activity_date) == date.date()
                    )
                ).first()
                
                if existing:
                    # Update existing record
                    for key, value in data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.sync_status = "completed"
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new record
                    summary = GarminDailySummary(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        activity_date=date,
                        sync_status="completed",
                        **data
                    )
                    session.add(summary)
                
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error storing daily summary for {user_id}: {e}")
            return False
    
    async def store_activity(self, user_id: str, activity_data: Dict[str, Any]) -> bool:
        """Store or update activity data using normalized Garmin fields."""
        try:
            garmin_activity_id = str(activity_data.get("activityId", ""))
            if not garmin_activity_id:
                self.logger.warning(f"Skipping activity store for {user_id}: missing activityId")
                return False

            activity_type = activity_data.get("activityType", {}) or {}
            start_time_local = activity_data.get("startTimeLocal", "")
            start_time = datetime.fromisoformat(start_time_local.replace("Z", "+00:00")) if start_time_local else datetime.utcnow()

            normalized = {
                "activity_name": activity_data.get("activityName", ""),
                "activity_type": activity_type.get("typeKey", "unknown"),
                "start_time": start_time,
                "duration_seconds": int(activity_data.get("duration", 0) or 0),
                "distance_km": (activity_data.get("distance", 0) or 0) / 1000 if activity_data.get("distance") else None,
                "avg_speed_kmh": (activity_data.get("averageSpeed", 0) or 0) * 3.6 if activity_data.get("averageSpeed") else None,
                "max_speed_kmh": (activity_data.get("maxSpeed", 0) or 0) * 3.6 if activity_data.get("maxSpeed") else None,
                "calories_burned": float(activity_data.get("calories", 0) or 0),
                "avg_heart_rate": int(activity_data.get("averageHeartRate", 0) or 0) if activity_data.get("averageHeartRate") else None,
                "max_heart_rate": int(activity_data.get("maxHeartRate", 0) or 0) if activity_data.get("maxHeartRate") else None,
                "elevation_gain_m": float(activity_data.get("elevationGain", 0) or 0) if activity_data.get("elevationGain") is not None else None,
                "raw_activity_data": activity_data,
            }

            with self.database.get_session() as session:
                existing = session.query(GarminActivity).filter(
                    GarminActivity.garmin_activity_id == garmin_activity_id
                ).first()

                if existing:
                    for key, value in normalized.items():
                        setattr(existing, key, value)
                else:
                    activity = GarminActivity(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        garmin_activity_id=garmin_activity_id,
                        **normalized,
                    )
                    session.add(activity)

                session.commit()
                return True

        except Exception as e:
            self.logger.error(f"Error storing activity for {user_id}: {e}")
            return False
    
    async def store_sleep_data(self, user_id: str, date: datetime, sleep_data: Dict[str, Any]) -> bool:
        """Store sleep data."""
        try:
            with self.database.get_session() as session:
                sleep = GarminSleep(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    sleep_date=date,
                    **sleep_data
                )
                session.add(sleep)
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error storing sleep data for {user_id}: {e}")
            return False
    
    async def store_heart_rate_data(self, user_id: str, date: datetime, hr_data: Dict[str, Any]) -> bool:
        """Store heart rate data."""
        try:
            with self.database.get_session() as session:
                hr = GarminHeartRate(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    recorded_at=date,
                    **hr_data
                )
                session.add(hr)
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error storing heart rate data for {user_id}: {e}")
            return False
    
    # Data Retrieval Tools
    
    async def get_daily_summaries(self, user_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get daily summaries for a date range."""
        try:
            with self.database.get_session() as session:
                summaries = session.query(GarminDailySummary).filter(
                    and_(
                        GarminDailySummary.user_id == user_id,
                        GarminDailySummary.activity_date >= start_date,
                        GarminDailySummary.activity_date <= end_date
                    )
                ).order_by(GarminDailySummary.activity_date).all()
                
                return [
                    {
                        "date": summary.activity_date,
                        "steps": summary.steps,
                        "calories_burned": summary.calories_burned,
                        "active_minutes": summary.active_minutes,
                        "distance_km": summary.distance_km,
                        "sleep_duration_hours": summary.sleep_duration_hours,
                        "sleep_quality_score": summary.sleep_quality_score,
                        "resting_heart_rate": summary.resting_heart_rate,
                        "avg_heart_rate": summary.avg_heart_rate,
                        "max_heart_rate": summary.max_heart_rate,
                        "stress_level_avg": summary.stress_level_avg,
                        "body_battery_level": summary.body_battery_level,
                        "vo2_max": summary.vo2_max,
                        "data_completeness_percentage": summary.data_completeness_percentage
                    } for summary in summaries
                ]
                
        except Exception as e:
            self.logger.error(f"Error getting daily summaries for {user_id}: {e}")
            return []
    
    async def get_recent_activities(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent activities for a user with normalized field names."""
        try:
            with self.database.get_session() as session:
                activities = session.query(GarminActivity).filter(
                    GarminActivity.user_id == user_id
                ).order_by(desc(GarminActivity.start_time)).limit(limit).all()
                
                return [
                    {
                        "id": str(activity.id),
                        "activity_type": activity.activity_type,
                        "activity_name": activity.activity_name,
                        "start_time": activity.start_time,
                        "duration_seconds": activity.duration_seconds,
                        "distance_km": activity.distance_km,
                        "calories_burned": activity.calories_burned,
                        "avg_heart_rate": activity.avg_heart_rate,
                        "max_heart_rate": activity.max_heart_rate,
                        "avg_speed_kmh": activity.avg_speed_kmh,
                        "elevation_gain_m": activity.elevation_gain_m,
                        "garmin_activity_id": activity.garmin_activity_id,
                        "raw_activity_data": activity.raw_activity_data,
                    } for activity in activities
                ]
                
        except Exception as e:
            self.logger.error(f"Error getting recent activities for {user_id}: {e}")
            return []

    async def get_activity_by_garmin_id(self, user_id: str, garmin_activity_id: str) -> Optional[Dict[str, Any]]:
        """Get a single activity by Garmin activity ID."""
        try:
            with self.database.get_session() as session:
                activity = session.query(GarminActivity).filter(
                    and_(
                        GarminActivity.user_id == user_id,
                        GarminActivity.garmin_activity_id == str(garmin_activity_id),
                    )
                ).first()

                if not activity:
                    return None

                return {
                    "id": str(activity.id),
                    "garmin_activity_id": activity.garmin_activity_id,
                    "activity_type": activity.activity_type,
                    "activity_name": activity.activity_name,
                    "start_time": activity.start_time,
                    "duration_seconds": activity.duration_seconds,
                    "distance_km": activity.distance_km,
                    "calories_burned": activity.calories_burned,
                    "avg_heart_rate": activity.avg_heart_rate,
                    "max_heart_rate": activity.max_heart_rate,
                    "avg_speed_kmh": activity.avg_speed_kmh,
                    "elevation_gain_m": activity.elevation_gain_m,
                    "raw_activity_data": activity.raw_activity_data,
                }
        except Exception as e:
            self.logger.error(f"Error getting activity by Garmin ID for {user_id}: {e}")
            return None
    
    # Caching Tools
    
    async def get_cached_response(self, user_id: str, query_type: str, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached AI response."""
        try:
            with self.database.get_session() as session:
                cache_entry = session.query(AIResponseCache).filter(
                    and_(
                        AIResponseCache.user_id == user_id,
                        AIResponseCache.query_type == query_type,
                        AIResponseCache.query_hash == query_hash,
                        AIResponseCache.expires_at > datetime.utcnow()
                    )
                ).first()
                
                if cache_entry:
                    # Update cache hit count
                    cache_entry.cache_hits += 1
                    session.commit()
                    
                    return {
                        "response_text": cache_entry.response_text,
                        "chart_data": cache_entry.chart_data,
                        "confidence_score": cache_entry.confidence_score,
                        "cache_hits": cache_entry.cache_hits
                    }
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting cached response: {e}")
            return None
    
    async def store_cached_response(self, user_id: str, query_type: str, query_hash: str, 
                                   response_text: str, chart_data: Optional[Dict[str, Any]] = None,
                                   confidence_score: Optional[float] = None,
                                   cache_duration_hours: int = 24) -> bool:
        """Store AI response in cache."""
        try:
            with self.database.get_session() as session:
                cache_entry = AIResponseCache(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    query_type=query_type,
                    query_hash=query_hash,
                    response_text=response_text,
                    chart_data=chart_data,
                    confidence_score=confidence_score,
                    expires_at=datetime.utcnow() + timedelta(hours=cache_duration_hours)
                )
                session.add(cache_entry)
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error storing cached response: {e}")
            return False
    
    # Monitoring and Analytics Tools
    
    async def log_api_usage(self, user_id: Optional[str], api_service: str, feature_used: str,
                           response_time_ms: float, success: bool = True, 
                           error_message: Optional[str] = None, tokens_used: Optional[int] = None,
                           estimated_cost_usd: Optional[float] = None) -> bool:
        """Log API usage for monitoring."""
        try:
            with self.database.get_session() as session:
                usage_log = APIUsageLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    api_service=api_service,
                    feature_used=feature_used,
                    response_time_ms=response_time_ms,
                    success=success,
                    error_message=error_message,
                    tokens_used=tokens_used,
                    estimated_cost_usd=estimated_cost_usd
                )
                session.add(usage_log)
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Error logging API usage: {e}")
            return False
    
    async def get_usage_statistics(self, user_id: Optional[str] = None, 
                                  days_back: int = 30) -> Dict[str, Any]:
        """Get usage statistics."""
        try:
            with self.database.get_session() as session:
                start_date = datetime.utcnow() - timedelta(days=days_back)
                
                query = session.query(APIUsageLog).filter(
                    APIUsageLog.created_at >= start_date
                )
                
                if user_id:
                    query = query.filter(APIUsageLog.user_id == user_id)
                
                logs = query.all()
                
                total_requests = len(logs)
                successful_requests = sum(1 for log in logs if log.success)
                total_tokens = sum(log.tokens_used for log in logs if log.tokens_used)
                total_cost = sum(log.estimated_cost_usd for log in logs if log.estimated_cost_usd)
                avg_response_time = sum(log.response_time_ms for log in logs) / total_requests if total_requests > 0 else 0
                
                return {
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "error_rate": (total_requests - successful_requests) / total_requests if total_requests > 0 else 0,
                    "total_tokens": total_tokens,
                    "total_cost_usd": total_cost,
                    "avg_response_time_ms": avg_response_time,
                    "period_days": days_back
                }
                
        except Exception as e:
            self.logger.error(f"Error getting usage statistics: {e}")
            return {}
    
    # Cleanup Tools
    
    async def cleanup_old_cache(self, days_old: int = 7) -> int:
        """Clean up old cache entries."""
        try:
            with self.database.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days_old)
                
                deleted = session.query(AIResponseCache).filter(
                    AIResponseCache.expires_at < cutoff_date
                ).delete()
                
                session.commit()
                return deleted
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old cache: {e}")
            return 0
    
    async def cleanup_old_conversations(self, days_old: int = 90) -> int:
        """Clean up old conversation data."""
        try:
            with self.database.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days_old)
                
                # Delete old messages
                deleted_messages = session.query(ConversationMessage).filter(
                    ConversationMessage.created_at < cutoff_date
                ).delete()
                
                # Delete old sessions
                deleted_sessions = session.query(ConversationSession).filter(
                    and_(
                        ConversationSession.session_end < cutoff_date,
                        ConversationSession.is_active == False
                    )
                ).delete()
                
                session.commit()
                return deleted_messages + deleted_sessions
                
        except Exception as e:
            self.logger.error(f"Error cleaning up old conversations: {e}")
            return 0


def get_database_tools(database: Database = None, config: Config = None) -> DatabaseTools:
    """Get or create database tools instance."""
    if not hasattr(get_database_tools, '_instance'):
        if not all([database, config]):
            raise ValueError("database and config are required for first initialization")
        get_database_tools._instance = DatabaseTools(database, config)
    return get_database_tools._instance


def init_database_tools(database: Database, config: Config) -> DatabaseTools:
    """Initialize and return database tools instance."""
    tools = DatabaseTools(database, config)
    get_database_tools._instance = tools
    return tools 